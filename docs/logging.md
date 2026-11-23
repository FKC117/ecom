# Operational logs

Django creates `logs/` at the repository root on startup. Override its absolute
location with `LOG_DIR`. Restart existing Django processes to activate changes.

- `requests.log`: every request reaching Django, including admin/API, with method,
  route pattern, status, elapsed time and generated request ID.
- `application.log`: Python application, Django, security and library INFO+ records.
- `errors.log`: ERROR+ records and failed requests. Exceptions include type and
  stack locations, without local variables, source lines or exception values.

Each line is JSON with a UTC timestamp, logger, source and process. The
`X-Request-ID` response header correlates a request with its logs. Logs are private
operational files; never serve this directory through Nginx or commit log data.

Arbitrary log messages are deliberately omitted because libraries can embed
credentials and customer data. Application code can supply a fixed `event` via
`logger.info('event', extra={'event': 'fixed_event_name'})`. Do not put user input
in event names. Request bodies, query strings, cookies, auth headers, raw paths,
SQL, and personal customer fields are not captured.

This captures emitted Python logging and Django requests, not every internal
function call, swallowed exception, browser event or database mutation. Existing
admin audit records remain in Django. Browser console and process stdout/stderr
are not redirected. Nginx-served assets/media do not pass through Django; production
Nginx access/error logs and service stdout/stderr need deployment configuration.
No production server configuration has been changed.

Production: restrict directory access to the service account and administrators.
Configure daily external logrotate with `rotate 14`, `compress`, `missingok`,
`notifempty` and `create 0600 <service-user> <service-group>` for the absolute
`logs/*.log` path. Use rename/create rotation, not copytruncate; handlers reopen
automatically. Rotation is not installed by local source changes. On Windows,
stop local Django before archiving/removing old logs. Monitor disk usage.
