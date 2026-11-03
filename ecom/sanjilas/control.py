"""Permission-checked JSON adapter for the actual Django admin registry.

ModelAdmin owns query scope, forms, fieldsets, permissions and save/delete hooks.
No public model serializer is used here. Custom inline/multivalue forms fail closed.
"""
import html
import json
from functools import wraps

from django import forms
from django.contrib import admin
from django.contrib.admin.utils import flatten_fieldsets, label_for_field, lookup_field
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, router, transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.html import strip_tags
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .branding import public_settings
from .control_copy import control_labels
from .models import SiteSettings
from .image_fields import WebPImageFormField
from .images import ACCEPT, image_metadata, limits, prepare_image


def active_operator(user):
    return user.is_authenticated and user.is_active and (user.is_staff or user.is_superuser)


def labels():
    settings = SiteSettings.load()
    return {**control_labels(), **settings.control_labels}


def api_error(key, status=400, **extra):
    return JsonResponse({"error": labels()[key], **extra}, status=status)


def csrf_failure(request, reason=""):
    if request.path.startswith('/api/shop/'):
        from .shop import fail
        return fail('shop_csrf',403)
    if request.path.startswith(("/api/control/", "/api/account/")):
        return api_error("csrf_error", 403)
    from django.views.csrf import csrf_failure as django_csrf_failure
    return django_csrf_failure(request, reason=reason)


def operator_required(view):
    @never_cache
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return api_error("session_expired", 401)
        if not active_operator(request.user):
            return api_error("permission_denied", 403)
        try:
            return view(request, *args, **kwargs)
        except PermissionDenied:
            return api_error("permission_denied", 403)
        except Http404:
            return api_error("not_found", 404)
        except ValidationError as error:
            return api_error("invalid_form", 400, errors=getattr(error, "message_dict", {"__all__": error.messages}))
        except IntegrityError:
            return api_error("invalid_form", 400)
    return wrapper


def resolve_admin(app_label, model_name):
    for model, model_admin in admin.site._registry.items():
        if (model._meta.app_label, model._meta.model_name) == (app_label, model_name):
            return model_admin
    raise Http404


def permissions(model_admin, request, obj=None):
    # Role/account grants remain privileged even if a staff user has change_user.
    auth_write = model_admin.model._meta.app_label != "auth" or request.user.is_superuser
    return {
        "view": model_admin.has_view_or_change_permission(request, obj),
        "add": auth_write and model_admin.has_add_permission(request),
        "change": auth_write and model_admin.has_change_permission(request, obj),
        "delete": auth_write and model_admin.has_delete_permission(request, obj),
    }


def admin_url(model_admin, action="changelist", obj=None):
    opts = model_admin.model._meta
    return reverse(f"admin:{opts.app_label}_{opts.model_name}_{action}", args=[obj.pk] if obj else None)


def descriptor(model_admin, request):
    opts = model_admin.model._meta
    p = permissions(model_admin, request)
    if not model_admin.has_module_permission(request) or not (p["view"] or p["add"]):
        return None
    return {
        "workspace": getattr(model_admin, "control_workspace", None),
        "menu_visible": getattr(model_admin, 'control_menu', True),
        "repeat_add": getattr(model_admin,'control_gallery',False),
        "parent_field": getattr(model_admin, 'control_parent_field', None),
        "parent_model": model_admin.model._meta.get_field(model_admin.control_parent_field).related_model._meta.label_lower if getattr(model_admin, 'control_parent_field', None) else None,
        "key": opts.label_lower, "app": opts.app_label, "model": opts.model_name,
        "name": str(opts.verbose_name), "name_plural": str(opts.verbose_name_plural),
        "app_name": str(opts.app_config.verbose_name), "permissions": p,
        "count": model_admin.get_queryset(request).count() if p["view"] else None,
        "searchable": bool(model_admin.get_search_fields(request)),
        "django_url": admin_url(model_admin),
        "import_url": admin_url(model_admin, "import") if hasattr(model_admin, "has_import_permission") and model_admin.has_import_permission(request) and p["change"] else None,
        "can_export": bool(hasattr(model_admin, "has_export_permission") and model_admin.has_export_permission(request) and p["view"]),
    }


@never_cache
@ensure_csrf_cookie
@require_GET
def session(request):
    from .operations import directory
    site = SiteSettings.load()
    allowed = active_operator(request.user)
    return JsonResponse({
        "site": public_settings(site, request), "labels": {**control_labels(), **site.control_labels},
        "csrf_token": get_token(request), "authenticated": allowed,
        "user": {"name": request.user.get_full_name() or request.user.get_username(), "superuser": request.user.is_superuser, "roles": list(request.user.groups.values_list("name", flat=True))} if allowed else None,
        "workspaces": directory(request) if allowed else [],
        "models": [item for ma in admin.site._registry.values() if (item := descriptor(ma, request))] if allowed else [],
    })


@never_cache
@require_POST
@sensitive_post_parameters("password")
def sign_in(request, *, customer_access=False):
    username = request.POST.get("username", "")[:254]
    user = authenticate(request, username=username, password=request.POST.get("password", ""))
    if user is None or not user.is_active or (not customer_access and not active_operator(user)):
        return api_error("account_invalid_login" if customer_access else "invalid_login", 400)
    login(request, user)
    return JsonResponse({"ok": True, "csrf_token": get_token(request)})


@operator_required
@require_POST
def sign_out(request):
    logout(request)
    return JsonResponse({"ok": True, "csrf_token": get_token(request)})


def safe_display(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    return strip_tags(str(value))


@operator_required
@require_GET
def records(request, app_label, model_name):
    ma = resolve_admin(app_label, model_name)
    if not ma.has_module_permission(request) or not permissions(ma, request)["view"]:
        raise PermissionDenied
    qs = ma.get_queryset(request)
    qs, duplicates = ma.get_search_results(request, qs, request.GET.get("q", "")[:200])
    if duplicates:
        qs = qs.distinct()
    if not qs.ordered:
        qs = qs.order_by(ma.model._meta.pk.name)
    page = Paginator(qs, 20).get_page(request.GET.get("page", 1))
    display = [name for name in ma.get_list_display(request) if name != "action_checkbox" and name != "password"]
    columns = [{"key": str(index), "label": str(label_for_field(name, ma.model, ma))} for index, name in enumerate(display)]
    rows = []
    for obj in page:
        p = permissions(ma, request, obj)
        if not p["view"]:
            continue
        rows.append({"id": str(obj.pk), "label": str(obj), "permissions": p, "cells": [safe_display(lookup_field(name, obj, ma)[2]) for name in display]})
    return JsonResponse({"model": descriptor(ma, request), "columns": columns, "rows": rows, "page": page.number, "pages": page.paginator.num_pages, "count": page.paginator.count})


def get_object(ma, request, pk):
    try:
        return get_object_or_404(ma.get_queryset(request), pk=pk)
    except (ValueError, ValidationError):
        raise Http404


def get_form(ma, request, obj):
    form = ma.get_form(request, obj, change=obj is not None and ma.has_change_permission(request, obj))
    # Never return a password hash to the browser. User creation passwords remain supported.
    if ma.model._meta.label_lower == "auth.user" and obj is not None:
        form = type("ControlUserForm", (form,), {"base_fields": {key: field for key, field in form.base_fields.items() if key != "password"}})
        form.base_fields.pop("password", None)
    return form


def form_schema(form, ma, request, obj):
    fields = []
    unsupported = bool(ma.get_inline_instances(request, obj))
    for name, field in form.fields.items():
        bound = form[name]
        value = bound.value()
        kind = "text"
        choices = []
        multiple = isinstance(field, (forms.ModelMultipleChoiceField, forms.MultipleChoiceField))
        if isinstance(field, forms.FileField):
            kind = "file"
        elif isinstance(field, forms.BooleanField):
            kind = "boolean"
        elif isinstance(field, forms.JSONField):
            kind = "json"
            if not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False, indent=2)
        elif isinstance(field, forms.ChoiceField) or isinstance(field, (forms.ModelChoiceField, forms.ModelMultipleChoiceField)):
            kind = "select"
            # Related choices use the same request-bound queryset as Django's form.
            if isinstance(field, (forms.ModelChoiceField, forms.ModelMultipleChoiceField)):
                # Large relations use a separate searchable options endpoint.
                choices = [{"value": str(field.prepare_value(item)), "label": str(field.label_from_instance(item))} for item in field.queryset[:100]]
                selected = value or [] if multiple else [value] if value else []
                present = {choice["value"] for choice in choices}
                missing = [str(item) for item in selected if str(item) not in present]
                if missing:
                    choices += [{"value": str(field.prepare_value(item)), "label": str(field.label_from_instance(item))} for item in field.queryset.filter(**{f"{field.to_field_name or 'pk'}__in": missing})]
            else:
                for key, text in field.choices:
                    if isinstance(text, (list, tuple)):
                        choices.extend({"value": str(k), "label": str(v)} for k, v in text)
                    else:
                        choices.append({"value": str(key), "label": str(text)})
        elif isinstance(field, forms.SplitDateTimeField):
            kind = "split_datetime"
            value = field.widget.decompress(value) if value else [None, None]
            value = [item.isoformat() if item else "" for item in value]
        elif isinstance(field, forms.MultiValueField):
            kind = "unsupported"
            unsupported = True
        elif isinstance(field, forms.DateTimeField):
            kind = "datetime-local"
        elif isinstance(field, forms.DateField):
            kind = "date"
        elif isinstance(field, forms.TimeField):
            kind = "time"
        elif isinstance(field, (forms.IntegerField, forms.DecimalField, forms.FloatField)):
            kind = "number"
        elif isinstance(field.widget, forms.PasswordInput):
            kind = "password"
            value = ""
        elif isinstance(field.widget, forms.Textarea):
            kind = "textarea"
        elif isinstance(field, forms.EmailField):
            kind = "email"
        elif isinstance(field, forms.URLField):
            kind = "url"
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        fields.append({
            "name": name, "label": str(field.label or name), "help": strip_tags(str(field.help_text)),
            "type": kind, "required": field.required, "disabled": field.disabled,
            "multiple": multiple, "choices": choices,
            "value": bool(value) if kind == "boolean" else "" if kind == "file" else value if value is not None else "",
            "file_url": value.url if kind == "file" and value else "",
            "is_image": isinstance(field, WebPImageFormField),
            "image_options": {**limits(), "accept": ACCEPT} if isinstance(field, WebPImageFormField) else None,
            "related": isinstance(field, (forms.ModelChoiceField, forms.ModelMultipleChoiceField)),
            "max_length": getattr(field, "max_length", None), "max_digits": getattr(field, "max_digits", None),
            "min": getattr(field, "min_value", None), "max": getattr(field, "max_value", None),
            "step": "1" if isinstance(field, forms.IntegerField) else "any",
        })
    readonly = []
    for name in ma.get_readonly_fields(request, obj):
        if name != "password" and obj is not None:
            readonly.append({"name": name, "label": str(label_for_field(name, ma.model, ma)), "value": safe_display(lookup_field(name, obj, ma)[2])})
    available = {field["name"] for field in fields} | {field["name"] for field in readonly}
    groups = []
    for title, options in ma.get_fieldsets(request, obj):
        names = [name for name in flatten_fieldsets([(title, options)]) if name in available]
        if names:
            groups.append({"title": str(title) if title else "", "fields": names})
    grouped = {name for group in groups for name in group["fields"]}
    if available - grouped:
        groups.append({"title": "", "fields": sorted(available - grouped)})
    return {"fields": fields, "readonly": readonly, "groups": groups, "advanced": unsupported}


@operator_required
@require_POST
def image_preview(request, app_label, model_name, field_name):
    ma = resolve_admin(app_label, model_name)
    obj = get_object(ma, request, request.POST["pk"]) if request.POST.get("pk") else None
    p = permissions(ma, request, obj)
    if not ma.has_module_permission(request) or not (p["change"] if obj is not None else p["add"]):
        raise PermissionDenied
    form = get_form(ma, request, obj)(instance=obj)
    field = form.fields.get(field_name)
    if not isinstance(field, WebPImageFormField) or field.disabled:
        raise PermissionDenied
    source = request.FILES.get("image") or (getattr(obj, field_name) if obj else None)
    if not source:
        raise ValidationError("Upload an image before editing it.")
    prepared = prepare_image(source, request.POST.get("edits", ""), icon_size=field.icon_size, variants=False)
    response = HttpResponse(prepared.read(), content_type="image/webp")
    response["X-Image-Width"] = str(prepared.width)
    response["X-Image-Height"] = str(prepared.height)
    return response


@operator_required
@require_http_methods(["GET", "POST"])
def record_form(request, app_label, model_name, pk=None):
    ma = resolve_admin(app_label, model_name)
    if not ma.has_module_permission(request):
        raise PermissionDenied
    obj = get_object(ma, request, pk) if pk is not None else None
    p = permissions(ma, request, obj)
    if not (p["view"] if obj else p["add"]):
        raise PermissionDenied
    form_class = get_form(ma, request, obj)
    if request.method == "POST":
        if not (p["change"] if obj else p["add"]):
            raise PermissionDenied
        # A generic UI must not silently drop custom inline controls.
        schema = form_schema(form_class(instance=obj), ma, request, obj)
        if schema["advanced"]:
            return api_error("advanced_form", 409)
        form = form_class(request.POST, request.FILES, instance=obj)
        if not form.is_valid():
            return api_error("invalid_form", errors={name: list(errors) for name, errors in form.errors.items()})
        with transaction.atomic(using=router.db_for_write(ma.model)):
            saved = ma.save_form(request, form, change=obj is not None)
            ma.save_model(request, saved, form, change=obj is not None)
            ma.save_related(request, form, [], change=obj is not None)
            message = ma.construct_change_message(request, form, [], add=obj is None)
            if obj is None:
                ma.log_addition(request, saved, message)
            else:
                ma.log_change(request, saved, message)
        return JsonResponse({"id": str(saved.pk), "message": labels()["saved"]})
    form = form_class(instance=obj)
    if obj is None:
        if getattr(ma,'control_gallery',False): form.initial.update(ma.get_changeform_initial_data(request))
        for name, field in form.fields.items():
            if isinstance(field, forms.ModelChoiceField) and request.GET.get(name):
                try:
                    form.initial[name] = field.clean(request.GET[name]).pk
                except ValidationError:
                    pass
    schema = form_schema(form, ma, request, obj)
    related = []
    if obj is not None or any(getattr(admin.site._registry.get(relation.related_model),'control_gallery',False) for relation in ma.model._meta.related_objects):
        for relation in ma.model._meta.related_objects:
            if not relation.one_to_many or relation.related_model not in admin.site._registry:
                continue
            child_admin = admin.site._registry[relation.related_model]
            gallery = getattr(child_admin,'control_gallery',False)
            if obj is None and not gallery: continue
            child = descriptor(child_admin, request)
            if not child:
                continue
            queryset = child_admin.get_queryset(request).filter(**{relation.field.name: obj}) if obj is not None else child_admin.get_queryset(request).none()
            records = []
            if child['permissions']['view']:
                for record in queryset[:100 if gallery else 30]:
                    p_child = permissions(child_admin,request,record)
                    if not p_child['view']: continue
                    row={'id':str(record.pk),'label':str(record),'permissions':p_child}
                    if gallery:
                        image=getattr(record,child_admin.control_image_field)
                        row.update(image=image.url if image else '',alt=record.image_alt,position=record.position,active=record.is_active)
                    records.append(row)
            related.append({'key': child['key'], 'name': labels()['gallery_title'] if gallery else child['name_plural'], 'field': relation.field.name,
                            'gallery':gallery,'group':getattr(child_admin,'control_group',None),
                            'add_label':getattr(child_admin,'control_add_label','add'),
                            'can_add': obj is not None and child['permissions']['add'],'records':records})
    schema['related'] = related
    return JsonResponse({"model": descriptor(ma, request), "id": str(obj.pk) if obj else None, "label": str(obj) if obj else "", "permissions": p, "django_url": admin_url(ma, "change", obj) if obj else admin_url(ma, "add"), **schema})


@operator_required
@require_GET
def field_options(request, app_label, model_name, field_name):
    ma = resolve_admin(app_label, model_name)
    obj = get_object(ma, request, request.GET["pk"]) if request.GET.get("pk") else None
    p = permissions(ma, request, obj)
    if not ma.has_module_permission(request) or not (p["view"] if obj else p["add"]):
        raise PermissionDenied
    field = get_form(ma, request, obj).base_fields.get(field_name)
    if not isinstance(field, (forms.ModelChoiceField, forms.ModelMultipleChoiceField)):
        raise Http404
    qs = field.queryset
    search = request.GET.get("q", "")[:100]
    related_admin = admin.site._registry.get(qs.model)
    if search and related_admin:
        qs, duplicate = related_admin.get_search_results(request, qs, search)
        if duplicate:
            qs = qs.distinct()
    elif search:
        qs = qs.filter(pk=search) if search.isdecimal() else qs.none()
    return JsonResponse({"choices": [{"value": str(field.prepare_value(item)), "label": str(field.label_from_instance(item))} for item in qs[:100]]})


@operator_required
@require_http_methods(["GET", "POST"])
def delete_record(request, app_label, model_name, pk):
    ma = resolve_admin(app_label, model_name)
    obj = get_object(ma, request, pk)
    if not ma.has_module_permission(request) or not permissions(ma, request, obj)["delete"]:
        raise PermissionDenied
    deleted, counts, missing, protected = ma.get_deleted_objects([obj], request)
    blocked = bool(missing or protected)
    if request.method == "GET":
        def plain_tree(items):
            return [plain_tree(item) if isinstance(item, (list, tuple)) else html.unescape(strip_tags(str(item))) for item in items]
        return JsonResponse({"label": str(obj), "related": plain_tree(deleted), "counts": {str(key): value for key, value in counts.items()}, "blocked": blocked})
    if blocked:
        return api_error("delete_blocked", 409)
    if request.POST.get("confirm") != "yes":
        return api_error("invalid_form")
    with transaction.atomic(using=router.db_for_write(ma.model)):
        ma.log_deletions(request, [obj])
        ma.delete_model(request, obj)
    return JsonResponse({"message": labels()["deleted"]})


@operator_required
@require_GET
def export_records(request, app_label, model_name):
    ma = resolve_admin(app_label, model_name)
    if not ma.has_module_permission(request) or not permissions(ma, request)["view"] or not hasattr(ma, "has_export_permission") or not ma.has_export_permission(request):
        raise PermissionDenied
    queryset = ma.get_export_queryset(request) if hasattr(ma, "get_export_queryset") else ma.get_queryset(request)
    queryset = queryset.filter(pk__in=ma.get_queryset(request).values("pk"))
    if queryset.count() > 10000:
        return api_error("export_limit", 413)
    ids = [obj.pk for obj in queryset if ma.has_view_or_change_permission(request, obj)]
    resource_class = ma.get_export_resource_classes(request)[0]
    resource = resource_class(**ma.get_export_resource_kwargs(request))
    dataset = resource.export(queryset=queryset.filter(pk__in=ids))
    # Spreadsheet formula characters are escaped before sending CSV downloads.
    for row in range(len(dataset)):
        dataset[row] = ["'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")) else value for value in dataset[row]]
    response = HttpResponse(dataset.csv, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{ma.model._meta.model_name}.csv"'
    return response


@never_cache
@ensure_csrf_cookie
@require_GET
def account_session(request):
    site = SiteSettings.load()
    copy = labels()
    copy.update(login_description=copy["account_login_description"],
                panel_name=copy["account_name"], roles_note=copy["account_roles_note"])
    authenticated = request.user.is_authenticated and request.user.is_active
    return JsonResponse({
        "site": public_settings(site, request), "labels": copy,
        "csrf_token": get_token(request), "authenticated": authenticated,
        "destination": "/control/" if active_operator(request.user) else "/account/",
        "user": {"name": request.user.get_full_name() or request.user.get_username()} if authenticated else None,
    })


@never_cache
@require_POST
@sensitive_post_parameters("password")
def account_login(request):
    return sign_in(request, customer_access=True)


@never_cache
@require_POST
def account_logout(request):
    logout(request)
    return JsonResponse({"ok": True, "csrf_token": get_token(request)})
