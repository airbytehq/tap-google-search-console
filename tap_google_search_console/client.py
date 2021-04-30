import json
from typing import Dict

import backoff
import requests

import singer
from google.oauth2 import service_account
from googleapiclient.discovery import Resource, build
from singer import utils


SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly", ]
LOGGER = singer.get_logger()


class Server5xxError(Exception):
    pass


class Server429Error(Exception):
    pass


class GoogleError(Exception):
    pass


class GoogleBadRequestError(GoogleError):
    pass


class GoogleUnauthorizedError(GoogleError):
    pass


class GooglePaymentRequiredError(GoogleError):
    pass


class GoogleNotFoundError(GoogleError):
    pass


class GoogleMethodNotAllowedError(GoogleError):
    pass


class GoogleConflictError(GoogleError):
    pass


class GoogleGoneError(GoogleError):
    pass


class GooglePreconditionFailedError(GoogleError):
    pass


class GoogleRequestEntityTooLargeError(GoogleError):
    pass


class GoogleRequestedRangeNotSatisfiableError(GoogleError):
    pass


class GoogleExpectationFailedError(GoogleError):
    pass


class GoogleForbiddenError(GoogleError):
    pass


class GoogleUnprocessableEntityError(GoogleError):
    pass


class GooglePreconditionRequiredError(GoogleError):
    pass


class GoogleInternalServiceError(GoogleError):
    pass


# Error Codes: https://developers.google.com/webmaster-tools/search-console-api-original/v3/errors
ERROR_CODE_EXCEPTION_MAPPING = {
    400: GoogleBadRequestError,
    401: GoogleUnauthorizedError,
    402: GooglePaymentRequiredError,
    403: GoogleForbiddenError,
    404: GoogleNotFoundError,
    405: GoogleMethodNotAllowedError,
    409: GoogleConflictError,
    410: GoogleGoneError,
    412: GooglePreconditionFailedError,
    413: GoogleRequestEntityTooLargeError,
    416: GoogleRequestedRangeNotSatisfiableError,
    417: GoogleExpectationFailedError,
    422: GoogleUnprocessableEntityError,
    428: GooglePreconditionRequiredError,
    500: GoogleInternalServiceError}


def get_exception_for_error_code(error_code):
    return ERROR_CODE_EXCEPTION_MAPPING.get(error_code, GoogleError)


def raise_for_error(response):
    try:
        response.raise_for_status()
    except (requests.HTTPError, requests.ConnectionError) as error:
        try:
            content_length = len(response.content)
            if content_length == 0:
                # There is nothing we can do here since Google has neither sent
                # us a 2xx response nor a response content.
                return
            response = response.json()
            if ('error' in response) or ('errorCode' in response):
                message = '%s: %s' % (response.get('error', str(error)),
                                      response.get('message', 'Unknown Error'))
                error_code = response.get('error', {}).get('code')
                ex = get_exception_for_error_code(error_code)
                raise ex(message)
            else:
                raise GoogleError(error)
        except (ValueError, TypeError):
            raise GoogleError(error)


class GoogleClient:
    def __init__(self, credentials_json: str, email: str):
        self._creds = None
        self._credentials_json = credentials_json
        self._admin_email = email
        self._service = None

    def _load_account_info(self) -> Dict:
        account_info = json.loads(self._credentials_json)
        return account_info

    def _obtain_creds(self) -> service_account.Credentials:
        account_info = self._load_account_info()
        creds = service_account.Credentials.from_service_account_info(account_info, scopes=SCOPES)
        self._creds = creds.with_subject(self._admin_email)

    def _construct_resource(self) -> Resource:
        if not self._creds:
            self._obtain_creds()
        self._service = build("searchconsole", "v1", credentials=self._creds)

    def _get_resource(self, name: str):
        if not self._service:
            self._construct_resource()
        return getattr(self._service, name)

    @backoff.on_exception(backoff.constant,
                          GoogleForbiddenError,
                          max_tries=2,  # Only retry once
                          interval=900,  # Backoff for 15 minutes in case of Quota Exceeded error
                          jitter=None)  # Interval value not consistent if jitter not None
    @backoff.on_exception(backoff.expo,
                          (Server5xxError, ConnectionError, Server429Error),
                          max_tries=7,
                          factor=3)
    # Rate Limit:
    #  https://developers.google.com/webmaster-tools/search-console-api-original/v3/limits
    @utils.ratelimit(1200, 60)
    def get(self, method_name, resource_name, params):
        resource = self._get_resource(resource_name)
        method = getattr(resource(), method_name)
        response = method(**params).execute()
        return response
