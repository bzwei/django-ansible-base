from urllib.parse import urlparse, urlunsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import load_pem_x509_certificate
from django.core.exceptions import ValidationError as LowLevelValidationError
from django.core.validators import URLValidator
from django.utils.translation import gettext_lazy as _
from rest_framework.serializers import ValidationError

VALID_STRING = _('Must be a valid string')


def validate_url_list(urls: list, schemes: list = ['https'], allow_plain_hostname: bool = False) -> None:
    if type(urls) is not list:
        raise ValidationError("Must be a list of urls")
    errors = []
    for a_url in urls:
        if type(a_url) is not str:
            errors.append(f"{a_url} must be a valid url")
            continue
        try:
            validate_url(a_url, schemes=schemes, allow_plain_hostname=allow_plain_hostname)
        except ValidationError:
            errors.append(f"{a_url} is invalid")
    if errors:
        raise ValidationError(', '.join(errors))


def validate_url(url: str, schemes: list = ['https'], allow_plain_hostname: bool = False) -> None:
    if type(url) is not str:
        raise ValidationError(VALID_STRING)
    if allow_plain_hostname:
        # The default validator will not allow names like https://junk so, if we are ok with simple hostnames we are going to munge up the URL for the validator
        try:
            url_parts = urlparse(url)
        except ValueError as e:
            raise ValidationError(str(e)) from e

        # Determine the user_info part of the URL
        user_info = ''
        if url_parts.username:
            user_info = url_parts.username
        if url_parts.password:
            user_info = f'{user_info}:{url_parts.password}'
        if user_info:
            user_info = f"{user_info}@"

        if url_parts.hostname and '.' not in url_parts.hostname:
            hostname = f'{url_parts.hostname}.localhost'
            port = f':{url_parts.port}' if url_parts.port else ''
            netloc = f"{user_info}{hostname}{port}"
            # Reconstruct and override the URL with a valid hostname
            url = urlunsplit([url_parts.scheme, netloc, url_parts.path, url_parts.query, url_parts.fragment])

    validator = URLValidator(schemes=schemes)
    try:
        validator(url)
    except LowLevelValidationError as e:
        raise ValidationError(e.message)


def validate_cert_with_key(public_cert_string, private_key_string):
    # Returns:
    # None if one of the parameters wasn't set
    # False if we failed to load an item (should be pre-tried by your serializer)
    # A ValidationError exception if the key/value don't match
    # True if everything checks out

    if not private_key_string or not public_cert_string:
        return None

    private_key = None
    public_cert = None
    try:
        private_key = serialization.load_pem_private_key(bytes(private_key_string, "UTF-8"), password=None)
        public_cert = load_pem_x509_certificate(bytes(public_cert_string, "UTF-8"))
    except Exception:
        return False

    try:
        # We have both pieces of the puzzle, lets make sure they interlock
        private_key.public_key().verify(
            public_cert.signature,
            public_cert.tbs_certificate_bytes,
            # Depends on the algorithm used to create the certificate
            padding.PKCS1v15(),
            public_cert.signature_hash_algorithm,
        )
    except InvalidSignature:
        raise ValidationError(_("The certificate and private key do not match"))
    except Exception as e:
        error = _("Unable to validate SP cert and key")
        if hasattr(e, 'message'):
            error = f"{error}: {e.message}"
        else:
            error = f"{error}: {e.__class__.__name__}"
        raise ValidationError(error)

    return True
