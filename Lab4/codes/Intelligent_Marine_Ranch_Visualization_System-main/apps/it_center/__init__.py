# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

from flask import Blueprint

blueprint = Blueprint(
    'it_center_blueprint',
    __name__,
    url_prefix='/it_center'
)