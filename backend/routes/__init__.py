"""
Trinity Backend - Routes Package
Flask Blueprints for modular endpoint organization

To use these blueprints, register them in the main app:
    from routes import health_bp, funding_bp, chat_bp, tools_bp, user_bp
    app.register_blueprint(health_bp)
    app.register_blueprint(funding_bp)
    ...
"""

from flask import Blueprint

# Create blueprints - these will be populated by route modules
health_bp = Blueprint('health', __name__)
funding_bp = Blueprint('funding', __name__)
chat_bp = Blueprint('chat', __name__)
tools_bp = Blueprint('tools', __name__)
user_bp = Blueprint('user', __name__)
generate_bp = Blueprint('generate', __name__)

# Note: Route modules should be imported AFTER blueprint creation
# to avoid circular imports. See routes/health.py for example.

__all__ = [
    'health_bp',
    'funding_bp', 
    'chat_bp',
    'tools_bp',
    'user_bp',
    'generate_bp'
]
