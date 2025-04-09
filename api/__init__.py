from flask import Blueprint

# This creates a Blueprint called 'api'
api = Blueprint('api', __name__)

# Import routes
from api import routes