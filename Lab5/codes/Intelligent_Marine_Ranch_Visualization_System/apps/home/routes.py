# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

from apps.home import blueprint
from flask import render_template, request
from flask_login import login_required, current_user
from jinja2 import TemplateNotFound


@blueprint.route('/index')
@login_required
def index():

    return render_template('home/index.html', segment='index', username=current_user.username)


@blueprint.route('/tables')
@blueprint.route('/tables.html')
@blueprint.route('/tables/')
@blueprint.route('/tables.htm')
@blueprint.route('/tables.html/')
@login_required
def admin_template():
    try:
        template = 'tables.html'
        if current_user.username != 'admin':
            return render_template('home/page-403.html'), 403

        # Detect the current page
        segment = get_segment(request)
        

        # Serve the file (if exists) from app/templates/home/admin.html
        return render_template("home/" + template, segment=segment, username=current_user.username)

    except TemplateNotFound:
        return render_template('home/page-404.html'), 404

    except:
        return render_template('home/page-500.html'), 500
    

@blueprint.route('/<template>')
@login_required
def route_template(template):

    try:

        if not template.endswith('.html'):
            template += '.html'

        # Detect the current page
        segment = get_segment(request)

        # Serve the file (if exists) from app/templates/home/FILE.html
        return render_template("home/" + template, segment=segment, username=current_user.username)

    except TemplateNotFound:
        return render_template('home/page-404.html'), 404

    except:
        return render_template('home/page-500.html'), 500


# Helper - Extract current page name from request
def get_segment(request):

    try:

        segment = request.path.split('/')[-1]

        if segment == '':
            segment = 'index'

        return segment

    except:
        return None
