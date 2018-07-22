"""Serves and automatically updates the pisoc website"""
import hashlib
import hmac
import logging
import os
import subprocess

import flask
import werkzeug

app = flask.Flask(__name__)
app.config['STATIC_FOLDER'] = 'hugo/public'
app.logger = logging.getLogger('gunicorn.error')
app.logger.setLevel(logging.INFO)


def serve_from_public(path_to_resource):
    """Serves from the "public" directory generated by hugo
    Code dervied from:
    https://github.com/pallets/flask/blob/master/flask/helpers.py#L681
    """
    filename = flask.helpers.safe_join('hugo/public', path_to_resource)

    if not os.path.isabs(filename):
        filename = os.path.join(flask.current_app.root_path, filename)

    try:
        # Linked to a resource
        if os.path.isfile(filename):
            return flask.helpers.send_file(filename, conditional=True)

        # Linked to a directory, serve the index for that dir
        if os.path.isdir(filename):
            return flask.helpers.send_file(filename + '/index.html', conditional=True)

        raise werkzeug.exceptions.NotFound()
    except (TypeError, ValueError):
        raise werkzeug.exceptions.BadRequest()


def pretty_log_stdout(stdout):
    """Logs a blob of text (proc stdouts) line-by-line"""
    for line in stdout.split('\n'):
        if line:
            app.logger.info(line)


@app.route('/')
def index():
    """Serves the index page"""
    return serve_from_public('index.html')


@app.route('/<path:path_to_resource>')
def other_resources(path_to_resource):
    """Serves all resources that are not /index.html"""
    return serve_from_public(path_to_resource)


@app.route('/' + os.getenv('PISOCNET_REBUILD_ENDPOINT'), methods=['POST'])
def rebuild():
    """Listens for payloads sent by Github's webhook system.
    Verifies the X-Hub-Signature header, as documented here:
    https://developer.github.com/webhooks/#delivery-headers

    If verification succeeds, the new version of the site is pulled from
    GitHub, and built with hugo.
    """
    predicted = 'sha1=' + hmac.new(
        os.getenv('PISOCNET_REBUILD_SECRET').encode(),
        flask.request.get_data(),
        hashlib.sha1
    ).hexdigest()

    received = flask.request.headers['X-Hub-Signature']

    app.logger.info(f'Predicted: {predicted}')
    app.logger.info(f'Received:  {received}')

    # XXX: A pull taking too long here might cause issues
    if hmac.compare_digest(predicted, received):
        options = {
            'stdout': subprocess.PIPE,
            'stderr': subprocess.STDOUT,
            'universal_newlines': True
        }

        app.logger.info('Pulling from git:')
        pretty_log_stdout(subprocess.run(
            'git pull'.split(),
            **options
        ).stdout)

        # BUG: Raw hugo stdout still making it to logs
        # [74B blob data], etc
        app.logger.info('Rebuilding site:')
        pretty_log_stdout(subprocess.run(
            'hugo --cleanDestinationDir -s hugo/'.split(),
            **options
        ).stdout)

    return ''


@app.errorhandler(404)
def page_not_found(_):
    """Serve 404.html when a 404 happens"""
    return serve_from_public('404.html'), 404