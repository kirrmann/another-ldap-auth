import sys
import json
from flask import Flask
from flask import request
from flask import g
from flask_httpauth import HTTPBasicAuth
from aldap import Aldap
from cache import Cache
from os import environ
from logs import Logs

# --- Logging -----------------------------------------------------------------
logs = Logs()

# --- Cache -------------------------------------------------------------------
CACHE_EXPIRATION = 5  # Expiration in minutes
if "CACHE_EXPIRATION" in environ:
	CACHE_EXPIRATION = int(environ["CACHE_EXPIRATION"])
cache = Cache(CACHE_EXPIRATION)

# --- Flask -------------------------------------------------------------------
app = Flask(__name__)
auth = HTTPBasicAuth()

@auth.verify_password
def login(username, password):
	if not username or not password:
		logs.error({'message': 'Username or password empty.'})
		return False

	try:
		# Get parameters from HTTP headers or from environment variables
		if "Ldap-Endpoint" in request.headers:
			LDAP_ENDPOINT = request.headers.get("Ldap-Endpoint")
		else:
			LDAP_ENDPOINT = environ["LDAP_ENDPOINT"]

		if "Ldap-Manager-Dn-Username" in request.headers:
			LDAP_MANAGER_DN_USERNAME = request.headers["Ldap-Manager-Dn-Username"]
		else:
			LDAP_MANAGER_DN_USERNAME = environ["LDAP_MANAGER_DN_USERNAME"]

		if "Ldap-Manager-Password" in request.headers:
			LDAP_MANAGER_PASSWORD = request.headers["Ldap-Manager-Password"]
		else:
			LDAP_MANAGER_PASSWORD = environ["LDAP_MANAGER_PASSWORD"]

		if "Ldap-Search-Base" in request.headers:
			LDAP_SEARCH_BASE = request.headers["Ldap-Search-Base"]
		else:
			LDAP_SEARCH_BASE = environ["LDAP_SEARCH_BASE"]

		if "Ldap-Search-Filter" in request.headers:
			LDAP_SEARCH_FILTER = request.headers["Ldap-Search-Filter"]
		else:
			LDAP_SEARCH_FILTER = environ["LDAP_SEARCH_FILTER"]

		# Optional parameter
		LDAP_REQUIRED_GROUPS = ""
		if "Ldap-Required-Groups" in request.headers:
			LDAP_REQUIRED_GROUPS = request.headers["Ldap-Required-Groups"]
		elif "LDAP_REQUIRED_GROUPS" in environ:
			LDAP_REQUIRED_GROUPS = environ["LDAP_REQUIRED_GROUPS"]

		# The default is "and", another option is "or"
		LDAP_REQUIRED_GROUPS_CONDITIONAL = "and"
		if "Ldap-Required-Groups-Conditional" in request.headers:
			LDAP_REQUIRED_GROUPS_CONDITIONAL = request.headers["Ldap-Required-Groups-Conditional"]
		elif "LDAP_REQUIRED_GROUPS_CONDITIONAL" in environ:
			LDAP_REQUIRED_GROUPS_CONDITIONAL = environ["LDAP_REQUIRED_GROUPS_CONDITIONAL"]

		# The default is "enabled", another option is "disabled"
		LDAP_REQUIRED_GROUPS_CASE_SENSITIVE = "enabled"
		if "Ldap-Required-Groups-Case-Sensitive" in request.headers:
			LDAP_REQUIRED_GROUPS_CASE_SENSITIVE = request.headers["Ldap-Required-Groups-Case-Sensitive"]
		elif "LDAP_REQUIRED_GROUPS_CASE_SENSITIVE" in environ:
			LDAP_REQUIRED_GROUPS_CASE_SENSITIVE = environ["LDAP_REQUIRED_GROUPS_CASE_SENSITIVE"]

		LDAP_SERVER_DOMAIN = ""
		if "Ldap-Server-Domain" in request.headers:
			LDAP_SERVER_DOMAIN = request.headers["Ldap-Server-Domain"]
		elif "LDAP_SERVER_DOMAIN" in environ:
			LDAP_SERVER_DOMAIN = environ["LDAP_SERVER_DOMAIN"]
	except KeyError as e:
		logs.error({'message': 'Invalid parameter'})
		return False

	# Create the ALDAP object
	aldap = Aldap (
		LDAP_ENDPOINT,
		LDAP_MANAGER_DN_USERNAME,
		LDAP_MANAGER_PASSWORD,
		LDAP_SERVER_DOMAIN,
		LDAP_SEARCH_BASE,
		LDAP_SEARCH_FILTER,
		LDAP_REQUIRED_GROUPS_CASE_SENSITIVE=='enabled',
		LDAP_REQUIRED_GROUPS_CONDITIONAL
	)

	# Initialize the ALDAP object
	# The username and password are from the Basic Authentication pop-up form
	aldap.setUser(username, password)

	# Check if the username and password are valid
	# First check inside the cache and then in the LDAP server
	if not cache.validateUser(username, password):
		if not aldap.authenticateUser():
			return False
		else:
			# Include the user in the cache after successfully authenticated
			cache.addUser(username, password)

	# Check groups only if they are defined
	matchesGroups = []
	if LDAP_REQUIRED_GROUPS:
		groups = LDAP_REQUIRED_GROUPS.split(",") # Split the groups by comma and trim
		groups = [x.strip() for x in groups] # Remove spaces
		#
		# TODO: Validate groups from cache
		#
		validGroups, matchesGroups = aldap.validateGroups(groups)
		if not validGroups:
			return False
		else:
			# Include the matches groups to the cache
			cache.addGroups(username, matchesGroups)

	# Success
	g.username = username # Set the username to send in the headers response
	g.matchesGroups = ','.join(matchesGroups) # Set the matches groups to send in the headers response
	return True

# Catch-All URL
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
@auth.login_required
def index(path):
	code = 200
	msg = "Another LDAP Auth"
	headers = [('x-username', g.username),('x-groups', g.matchesGroups)]
	return msg, code, headers

# Main
if __name__ == '__main__':
	app.run(host='0.0.0.0', port=9000, debug=False)
