from typing import List

import os
# import argparse
import logging
import requests
import pymongo # type: ignore[import]
from .O2Phones.scraper import pipeline

LOGGER = logging.getLogger(__name__)


def send_email(
        *, subject: str, html: str, emails: List[str],
        mailgun_url: str, api_key: str
    ):
    data={
        'from': 'me@foo.bar',
        'to': emails,
        'subject': subject,
        'html': html
    }
    LOGGER.info('Sending email')
    r = requests.post(mailgun_url, auth=('api', api_key), data=data)
    return r



def main():
    fmt = '%(levelname)s - %(name)s - %(message)s'
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - {}'.format(fmt)
    )

    # parser = argparse.ArgumentParser()
    # args = parser.parse_args()

    client = pymongo.MongoClient(os.environ['MONGO_URI'])
    db = client.get_default_database()
    o2phone = pipeline(db)
    if o2phone:
        r = send_email(
            subject='O2 Phone Deals',
            html=o2phone,
            emails=os.environ['EMAILS'].split(' '),
            mailgun_url=os.environ['MAILGUN'],
            api_key=os.environ['API_KEY'],
        )
        assert r.status_code == 200
    client.close()
    LOGGER.info('Done')

if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Exception goes to logger handler e.g. Sentry
        LOGGER.exception('Something went wrong')
        raise
