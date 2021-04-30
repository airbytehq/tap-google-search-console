#!/usr/bin/env python3

import sys
import json
import singer
from tap_google_search_console.client import GoogleClient
from tap_google_search_console.discover import discover
from tap_google_search_console.sync import sync

LOGGER = singer.get_logger()

REQUIRED_CONFIG_KEYS = [
    'credentials_json',
    'email',
    'site_urls',
    'start_date',
    'user_agent'
]


def do_discover():
    LOGGER.info('Starting discover')
    catalog = discover()
    json.dump(catalog.to_dict(), sys.stdout, indent=2)
    LOGGER.info('Finished discover')


@singer.utils.handle_top_exception(LOGGER)
def main():
    parsed_args = singer.utils.parse_args(REQUIRED_CONFIG_KEYS)

    google_client = GoogleClient(parsed_args.config['credentials_json'], parsed_args.config['email'])

    state = {}
    if parsed_args.state:
        state = parsed_args.state

    if parsed_args.discover:
        do_discover()
    elif parsed_args.catalog:
        sync(client=google_client,
             config=parsed_args.config,
             catalog=parsed_args.catalog,
             state=state)


if __name__ == '__main__':
    main()
