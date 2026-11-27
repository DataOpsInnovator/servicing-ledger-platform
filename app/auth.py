"""Validate access tokens against explicitly configured issuer, audience and JWKS."""
from dataclasses import dataclass
import hashlib
import hmac
import jwt


@dataclass(frozen=True)
class Principal:
    roles: frozenset[str]
    actor: str


class InvalidToken(Exception):
    pass


class Authenticator:
    def __init__(self, settings, jwks=None):
        self.settings = settings
        self.jwks = jwks or (jwt.PyJWKClient(settings.oidc_jwks_url, timeout=4, lifespan=300)
                            if settings.oidc_jwks_url else None)

    def authenticate(self, token):
        if not token or len(token) > 8192:
            raise InvalidToken
        if self.jwks:
            try:
                key = self.jwks.get_signing_key_from_jwt(token).key
                claims = jwt.decode(token, key, algorithms=['RS256'], audience=self.settings.oidc_audience,
                                    issuer=self.settings.oidc_issuer,
                                    options={'require': ['exp','iat','iss','aud','sub']}, leeway=15)
                scopes = claims.get('scope', '')
                if not isinstance(scopes, str) or not isinstance(claims['sub'], str) or not claims['sub']:
                    raise InvalidToken
                roles = frozenset(role for role, scope in [('writer','ledger:write'),('operator','ledger:operate')]
                                  if scope in scopes.split())
                actor = 'oidc:' + hashlib.sha256((claims['iss']+'\0'+claims['sub']).encode()).hexdigest()
                return Principal(roles, actor)
            except (jwt.PyJWTError, ValueError, TypeError):
                raise InvalidToken from None
        for role, expected in [('writer', self.settings.writer_token), ('operator', self.settings.operator_token)]:
            if expected and hmac.compare_digest(token.encode(), expected.encode()):
                return Principal(frozenset([role]), 'local:'+role)
        raise InvalidToken
