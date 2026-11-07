from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import EmbedLink

# What the embedded Servicios view calls: the agenda, quote requests, and the product dialog. Nothing else accepts
# the link, so it can't reach sales, commissions or account management even if its account had the role.
EMBED_PATHS = ('/api/auth/me/', '/api/servicios/', '/api/solicitudes/', '/api/inventory/', '/api/gea-parts/')


class EmbedLinkAuthentication(BaseAuthentication):
    """The X-Embed-Key header (from the embed page's ?k=) as the link's account. No CSRF check: a header a page
    can't make another site's browser send is itself the proof (unlike a cookie)."""

    def authenticate(self, request):
        key = request.headers.get('X-Embed-Key')
        if not key or not request.path.startswith(EMBED_PATHS):
            return None
        link = EmbedLink.objects.select_related('user').filter(token=key, user__is_active=True).first()
        if not link:
            raise AuthenticationFailed('Enlace no válido o revocado.')
        return link.user, link
