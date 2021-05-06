import json
from typing import Dict

import backoff

from google.oauth2 import service_account
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from singer import utils

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly", ]


def quota_exceeded_handling(error):
    return error.resp.status != 403


def error_handling(error):
    return not (error.resp.status == 429 or error.resp.status >= 500)


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
                          HttpError,
                          max_tries=2,  # Only retry once
                          interval=900,  # Backoff for 15 minutes in case of Quota Exceeded error
                          jitter=None,  # Interval value not consistent if jitter not None
                          giveup=quota_exceeded_handling)
    @backoff.on_exception(backoff.expo,
                          HttpError,
                          max_tries=7,
                          factor=3,
                          giveup=error_handling)
    # Rate Limit:
    #  https://developers.google.com/webmaster-tools/search-console-api-original/v3/limits
    @utils.ratelimit(1200, 60)
    def get(self, method_name, resource_name, params):
        resource = self._get_resource(resource_name)
        method = getattr(resource(), method_name)
        response = method(**params).execute()
        return response
