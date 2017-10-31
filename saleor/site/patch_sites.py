import threading

from django.contrib.sites.models import SiteManager
from django.core.exceptions import ImproperlyConfigured
from django.http.request import split_domain_port


'''
We are patching django.contrib.sites because it is cached on module level and
can be in some cases thread unsafe. Also django.contrib.sites can be used by
other modules and we don't want to lose its functionality. Saleor has its own
SiteSetting, but having those settings in two places is not what we wanted.
Instead we link django.contrib.sites and saleor Site.Settings with One To One
relationship.
In this patch we are also prefetching our settings for better performance.
'''


lock = threading.Lock()
with lock:
    THREADED_SITE_CACHE = {}


def new_get_current(self, request=None):
    print "new get current"
    from django.conf import settings
    if getattr(settings, 'SITE_ID', ''):
        site_id = settings.SITE_ID
        if site_id not in THREADED_SITE_CACHE:
            with lock:
                site = self.prefetch_related('settings').filter(pk=site_id)[0]
                THREADED_SITE_CACHE[site_id] = site
        return THREADED_SITE_CACHE[site_id]
    elif request:
        host = request.get_host()
        try:
            # First attempt to look up the site by host with or without port.
            if host not in THREADED_SITE_CACHE:
                with lock:
                    site = self.prefetch_related('settings').filter(
                        domain__iexact=host)[0]
                    THREADED_SITE_CACHE[host] = site
            return THREADED_SITE_CACHE[host]
        except Site.DoesNotExist:
            # Fallback to looking up site after stripping port from the host.
            domain, port = split_domain_port(host)
            if domain not in THREADED_SITE_CACHE:
                with lock:
                    site = self.prefetch_related('settings').filter(
                        domain__iexact=domain)[0]
                    THREADED_SITE_CACHE[domain] = site
        return THREADED_SITE_CACHE[domain]

    raise ImproperlyConfigured(
        "You're using the Django \"sites framework\" without having "
        "set the SITE_ID setting. Create a site in your database and "
        "set the SITE_ID setting or pass a request to "
        "Site.objects.get_current() to fix this error."
    )


def new_clear_cache(self):
    global THREADED_SITE_CACHE
    with lock:
        THREADED_SITE_CACHE = {}


def new_get_by_natural_key(self, domain):
    return self.prefetch_related('settings').filter(domain__iexact=domain)[0]


def patch_contrib_sites():
    SiteManager.get_current = new_get_current
    SiteManager.clear_cache = new_clear_cache
    SiteManager.get_by_natural_key = new_get_by_natural_key
