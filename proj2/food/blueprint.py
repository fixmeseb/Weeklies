"""The food blueprint. Its routes are spread over this package; proj2.food.views loads them."""

from flask import Blueprint

bp = Blueprint("food", __name__)
