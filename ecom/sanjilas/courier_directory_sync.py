"""One staff action imports the complete hierarchy; publish only after full success."""
import logging
import threading
import time
from datetime import timedelta
from types import SimpleNamespace
from django.contrib import admin
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import close_old_connections,transaction
from django.http import HttpRequest
from django.utils import timezone
from .models import CourierAccount,CourierDirectorySync,CourierLocation,CourierLocationImport
from .couriers import adapter,CourierError
from .shipments import fetch_location_choices

_worker_lock=threading.Lock()


def status(job):
    return {'id':job.pk,'state':job.state,'state_label':job.get_state_display(),'cities':job.cities,'zones':job.zones,
            'can_resume':job.state in ('queued','running') and job.next_attempt_at<=timezone.now() and job.updated_at < timezone.now()-timedelta(minutes=2),
            'next_attempt_at':job.next_attempt_at,
            'staging_url':f'/admin/sanjilas/courierlocationimport/?sync__id__exact={job.pk}',
            'areas':job.areas,'processed_cities':job.processed_cities,'processed_zones':job.processed_zones,
            'last_error':job.last_error,'updated_at':job.updated_at}


def _check_location_scope(request,account):
    ma=admin.site._registry[CourierLocation]
    visible=ma.get_queryset(request).filter(account=account)
    if CourierLocation.objects.filter(account=account).exclude(pk__in=visible.values('pk')).exists(): raise PermissionDenied
    if any(not ma.has_change_permission(request,row) for row in visible.iterator()): raise PermissionDenied


def enqueue(request,account):
    from .courier_directory import can_refresh
    if not can_refresh(request,account): raise PermissionDenied
    _check_location_scope(request,account)
    with transaction.atomic():
        CourierAccount.objects.select_for_update().get(pk=account.pk)
        job=CourierDirectorySync.objects.filter(account=account,state__in=['queued','running']).first()
        if job is None:
            job=CourierDirectorySync.objects.filter(account=account,state='failed').order_by('-created_at').first()
            if job:
                job.state='queued';job.last_error='';job.requested_by=request.user;job.save()
            else: job=CourierDirectorySync.objects.create(account=account,requested_by=request.user)
            admin.site._registry[CourierAccount].log_change(request,account,'Requested complete city, zone and area directory refresh.')
        transaction.on_commit(start_worker)
    return job


def start_worker():
    if not _worker_lock.acquire(blocking=False): return
    def run():
        try:
            close_old_connections()
            drain_pending()
        except Exception:
            logging.getLogger(__name__).exception('Courier directory worker stopped; pending work remains resumable.')
        finally:
            close_old_connections();_worker_lock.release()
    try: threading.Thread(target=run,name='courier-directory-import',daemon=True).start()
    except Exception:
        _worker_lock.release()
        raise


def drain_pending():
    while True:
        if process_one(): continue
        upcoming=CourierDirectorySync.objects.filter(state__in=['queued','running']).order_by('next_attempt_at').values_list('next_attempt_at',flat=True).first()
        if upcoming is None: return
        # Sleep outside the database transaction; no row lock is held during cooldown.
        time.sleep(max(1,min(30,(upcoming-timezone.now()).total_seconds())))


def _stage(job,kind,parent=None):
    for attempt in range(3):
        try:
            choices=fetch_location_choices(adapter(job.account),kind,parent)
            break
        except CourierError as error:
            if not error.retryable or attempt==2: raise
            time.sleep(max(job.request_interval,attempt+1))
    ids=[row['id'] for row in choices]
    if len(ids)!=len(set(ids)) or (kind=='cities' and not choices):
        raise ValidationError('Courier returned an invalid directory. Existing locations remain unchanged.')
    CourierLocationImport.objects.bulk_create([CourierLocationImport(sync=job,kind=kind,external_id=row['id'],
        parent_external_id=parent,name=row['name'],available=row['available']) for row in choices],batch_size=500)
    setattr(job,kind,getattr(job,kind)+len(choices))
    job.next_attempt_at=timezone.now()+timedelta(seconds=job.request_interval)
    job.rate_limit_hits=0
    job.last_error=''


def _publish(job,request):
    _check_location_scope(request,job.account)
    account=CourierAccount.objects.select_for_update().get(pk=job.account_id)
    now=timezone.now()
    CourierLocation.objects.filter(account=account).update(is_active=False)
    parents={}
    for kind in ('cities','zones','areas'):
        staged=list(job.records.filter(kind=kind))
        rows=[CourierLocation(account=account,kind=kind,external_id=row.external_id,name=row.name,
             available=row.available,is_active=True,parent_id=parents[row.parent_external_id] if row.parent_external_id is not None else None,
             children_refreshed_at=now if kind!='areas' else None) for row in staged]
        CourierLocation.objects.bulk_create(rows,update_conflicts=True,
            unique_fields=['account','kind','external_id'],update_fields=['name','available','is_active','parent','children_refreshed_at'],batch_size=500)
        parents=dict(CourierLocation.objects.filter(account=account,kind=kind,is_active=True).values_list('external_id','pk'))
    CourierAccount.objects.filter(pk=account.pk).update(cities_refreshed_at=now)
    job.state='completed';job.stage='done'
    admin.site._registry[CourierAccount].log_change(request,account,
        f'Complete directory refreshed: {job.cities} cities, {job.zones} zones, {job.areas} areas.')
    # Staging is only needed while a job is pending or resumable.
    job.records.all().delete()


def process_one():
    with transaction.atomic():
        job=CourierDirectorySync.objects.select_for_update(skip_locked=True).filter(state__in=['queued','running'],next_attempt_at__lte=timezone.now()).order_by('created_at').first()
        if job is None: return False
        try:
            with transaction.atomic():
                from .courier_directory import can_refresh
                request=HttpRequest();request.method='POST';request.path='/api/control/courier-directory/refresh/'
                request.user=job.requested_by
                request.resolver_match=SimpleNamespace(url_name='courier-directory-refresh')
                if not request.user.is_active or not (request.user.is_staff or request.user.is_superuser) or not can_refresh(request,job.account):
                    raise PermissionDenied
                if not admin.site._registry[CourierAccount].get_queryset(request).filter(pk=job.account_id).exists(): raise PermissionDenied
                job.state='running'
                if job.stage=='cities':
                    _stage(job,'cities');job.stage='zones'
                elif job.stage=='zones':
                    city=job.records.filter(kind='cities',children_fetched=False).order_by('external_id').first()
                    if city:
                        _stage(job,'zones',city.external_id);city.children_fetched=True;city.save();job.processed_cities+=1
                    else: job.stage='areas'
                elif job.stage=='areas':
                    zone=job.records.filter(kind='zones',children_fetched=False).order_by('external_id').first()
                    if zone:
                        _stage(job,'areas',zone.external_id);zone.children_fetched=True;zone.save();job.processed_zones+=1
                    else: job.stage='publish'
                elif job.stage=='publish': _publish(job,request)
                else: raise ValidationError('Unknown directory import stage.')
                job.save()
        except Exception as error:
            # Reload counters after the savepoint rollback. Never publish partial data.
            job.refresh_from_db()
            if isinstance(error,CourierError) and error.http_status==429:
                job.rate_limit_hits+=1
                delay=max(error.retry_after or 0,min(900,60*2**min(job.rate_limit_hits-1,4)))
                job.request_interval=min(60,max(5,job.request_interval*2))
                job.next_attempt_at=timezone.now()+timedelta(seconds=delay)
                job.state='running'
                job.last_error=f'Courier rate limit reached. Waiting {delay} seconds before resuming automatically. Imported progress is saved.'
                job.save()
                return True
            if isinstance(error,CourierError):
                reason=(f'Courier refused the request (HTTP {error.http_status}).' if error.http_status else 'Courier connection failed or timed out.')
            elif isinstance(error,PermissionDenied): reason='Permission to update the courier directory was denied.'
            elif isinstance(error,ValidationError): reason='Courier returned an invalid location directory.'
            else:
                reason='Could not save the imported directory.'
                logging.getLogger(__name__).exception('Directory import %s failed at %s',job.pk,job.stage)
            parent_kind={'zones':'cities','areas':'zones'}.get(job.stage)
            pending=job.records.filter(kind=parent_kind,children_fetched=False).order_by('external_id').first() if parent_kind else None
            context=f'{job.stage}: {pending.name[:60]}' if pending else job.stage
            job.state='failed';job.last_error=f'{reason} Stage: {context}. Existing locations are unchanged. Retry resumes saved progress.';job.save()
    return True
