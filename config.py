import os
from urllib.parse import urlparse
token = os.environ.get('TGTOKEN', '')
port = int(os.environ.get('PORT', 8443))
placeholder = 'data:image/gif;base64,' + \
    'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
db_url = urlparse(os.environ.get("DATABASE_URL"))
