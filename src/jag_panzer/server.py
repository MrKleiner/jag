import socket, threading, time, sys, hashlib, json, base64, struct, io, multiprocessing, os, datetime
from pathlib import Path
import traceback

# important todo: wat ?
# (this library simply has to be a proper package)
sys.path.append(str(Path(__file__).parent))

from jag_http_session import htsession
import jag_util
from jag_util import JagConfigBase, NestedProcessControl, conlog, DynamicGroupedText

from easy_timings.mstime import perftest

import jag_http_ents



# Path
# jag_util
# socket
# threading
# time
# sys
# hashlib
# json
# base64
# struct
# io
# multiprocessing
class pylib_preload:
	"""
	Precache python libraries.
	Cry all you want, but this reduces disk load
	"""
	def __init__(self):
		import socket
		import threading
		import time
		import sys
		import hashlib
		import json
		import base64
		import struct
		import io
		import multiprocessing
		import traceback
		import urllib
		import math
		import datetime

		from pathlib import Path

		import jag_util

		self.jag_util =  jag_util

		self.Path =      Path
		self.socket =    socket
		self.threading = threading
		self.time =      time
		self.sys =       sys
		self.hashlib =   hashlib
		self.json =      json
		self.base64 =    base64
		self.struct =    struct
		self.io =        io
		self.traceback = traceback
		self.urllib =    urllib
		self.math =      math
		self.datetime =  datetime



# sysroot         = Path-like pointing to the root of the jag package
# pylib           = A bunch of precached python packages
# mimes           = A dictionary of mime types; {file_ext:mime}
#                   | regular = {file_ext:mime}
#                   | signed =  {.file_ext:mime}
# response_codes  = HTTP response codes {code(int):string_descriptor}
# reject_precache = HTML document which sez "access denied"
# cfg             = Server Config
# doc_root        = Server Document Root
# list_dir        = List directory as html document
class JagHTTPServerResources(JagConfigBase):
	"""
	Server info.
	This class contains the config itself,
	some preloaded python libraries,
	and other stuff
	"""
	def __init__(self, init_config=None):
		from mimes.mime_types_base import base_mimes
		from mimes.mime_types_base import base_mimes_signed
		from response_codes import codes as http_response_codes

		from pathlib import Path
		import jag_util, io, platform

		# todo: obsolete. Delete this
		self.devtime = 0
		# timestamp of the 
		self.tstamp = None

		# root of the python package
		self.sysroot = Path(__file__).parent

		# mimes
		self.mimes = {
			'regular': base_mimes,
			'signed': base_mimes_signed,
		}

		# HTTP response codes
		self.response_codes = http_response_codes

		# Reject html document precache
		self.reject_precache = (self.sysroot / 'assets' / 'reject.html').read_bytes()


		# ------------------
		# base config
		# ------------------
		self.create_base(
			{
				# Port to run the server on
				'port': 0,

				# Document root (where index.html is)
				'doc_root': None,

				# This path should point to a python file with "main()" function inside
				# If nothing is specified, then default room is created
				'room_file': None,

				# Could possibly be treated as bootleg anti-ddos/spam
				'max_connections': 0,

				# https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Server-Timing
				'enable_web_timing_api': False,

				# custom context, must be picklable if multiprocessing is used 
				'context': None,

				# The name of the html file to serve when request path is '/'
				'root_index': None,
				'enable_indexes': True,
				'index_names': ['index.html'],
			},
			init_config
		)
		self.doc_root = Path(self.cfg['doc_root'])
		self.context = self.cfg['context']



		# ------------------
		# Directory Listing
		# ------------------
		self.reg_cfg_group(
			'dir_listing',
			{
				'enabled': False,
				'dark_theme': False,
			}
		)


		# ------------------
		# Errors
		# ------------------
		self.reg_cfg_group(
			'errors',
			{
				# echo exceptions to client
				'echo_to_client': False,
			}
		)


		# ------------------
		# Buffer sizes
		# ------------------
		self.reg_cfg_group(
			'buffers',
			{
				# Max file size when serving a file through built-in server services
				# Default to 8mb
				'max_file_len': (1024**2)*8,

				# Max size of the header buffer
				# Default to 512kb
				'max_header_len': 1024*512,

				# Default size of a single chunk when streaming buffers
				# Default to 5mb
				'bufstream_chunk_len': (1024**2)*5,

				# Max size of a single chunk when reading streams.
				# Should not be changed unless you know what you're doing
				'stream_receive': 4096,
			}
		)


		# ------------------
		# multiprocessing
		# ------------------

		# Multiprocessing takes away the privilege of shared context
		# among requests,
		# but multiprocessing is the only way to
		# serve many requests without hanging the server.

		# Single threaded server is perfect for small internal use
		# applications, like hosting some sort of a control panel.
		self.reg_cfg_group(
			'multiprocessing',
			{
				# enable the feature
				'enabled': True,

				# the amount of workerks listening for requests
				# default to the amount of CPU cores, capped to a range 2-16
				'worker_count': jag_util.clamp(os.cpu_count() or 2, 2, 16),
			}
		)


		# ------------------
		# Logging
		# ------------------

		# default log dirs
		logdir_selector = {
			'linux': Path('/var/log/jag'),
			'windows': Path(Path.home() / 'AppData' / 'Roaming' / 'jag' / 'log'),
		}
		self.reg_cfg_group(
			'logging',
			{
				# whether to enable file logging feature or not
				# this does not prevent the logging server from starting
				# log messages are simply not being sent to the server
				'enabled': True,

				# path to the folder where logs are stored
				# Linux default: /var/log/jag
				# Windows default: %appdata%/Roaming/jag/log
				'logs_dir': None,

				# The RPC port of the logger
				# DO NOT TOUCH !
				'port': None,
			}
		)

		# ensure the default folder exists
		if self.cfg['logging']['logs_dir'] == None:
			self.cfg['logging']['logs_dir'] = logdir_selector[platform.system().lower()]
			self.cfg['logging']['logs_dir'].mkdir(parents=True, exist_ok=True)


	def reload_libs(self):
		# preload python libraries
		self.pylib = pylib_preload()







def server_worker(skt, sv_resources, worker_idx):
	sv_resources.reload_libs()

	custom_room_func = None
	if sv_resources.cfg['room_file']:
		route_index = JagRoutingIndex(sv_resources.cfg['room_file'])
		route_index.find_routes()

	print(f"""Worker {worker_idx+1}/{sv_resources.cfg['multiprocessing']['worker_count']} initialized""")
	while True:
		conn, address = skt.accept()
		# print('Worker', worker_idx, 'accepted connection')
		sv_resources.devtime = time.time()
		threading.Thread(target=htsession, args=(conn, address, sv_resources, route_index), daemon=True).start()



_server_proc = '[Server Process]'
def sock_server(sv_resources):
	print('SKT Server PID:', os.getpid())
	print(_server_proc, 'Binding server to a port... (5/7)')
	# Port to run the server on
	# port = 56817
	port = sv_resources.cfg['port']
	# Create the Server object
	skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

	skt.bind(
		('', port)
	)

	# Basically launch the server
	# The number passed to this function identifies the max amount of simultaneous connections.
	# If the amount of connections exceeds this limit -
	# connections become rejected till other ones are resolved (aka closed)
	# 0 = infinite
	skt.listen(sv_resources.cfg['max_connections'])

	print(_server_proc, 'Server listening on port (6/7)', skt.getsockname()[1])

	if sv_resources.cfg['multiprocessing']['enabled']:
		for proc in range(sv_resources.cfg['multiprocessing']['worker_count']):
			multiprocessing.Process(target=server_worker, args=(skt, sv_resources, proc)).start()
		print(_server_proc, 'Accepting connections... (7/7)')
	else:
		sv_resources.reload_libs()
		print(_server_proc, 'Accepting connections... (7/7)')
		while True:
			conn, address = skt.accept()
			sv_resources.devtime = time.time()
			threading.Thread(target=htsession, args=(conn, address, sv_resources), daemon=True).start()



def logger_process(sv_resources, sock_obj):
	import jag_logging
	jag_logging.gestapo(sv_resources, sock_obj)



# Main process of the entire system
# It launches the server itself and everything else
_main_init = '[root]'
def server_process(sv_resources, stfu=False):
	print('Main Process PID:', os.getpid())
	os.environ['_jag-dev-lvl'] = '1'

	# try overriding dev level
	try:
		os.environ['_jag-dev-lvl'] = str(int(sv_resources.cfg['console_echo_level']))
	except Exception as e:
		pass

	# Preload resources n stuff
	print(_main_init, 'Initializing resources... (1/7)')

	# logging
	os.environ['jag_logging_port'] = 'False'
	if sv_resources.cfg['logging']['enabled']:
		print(_main_init, 'Winding up logging (1.1/7)...')

		# reserve a port for the logger
		logging_socket = socket.socket()
		logging_socket.bind(('127.0.0.1', 0))
		sv_resources.cfg['logging']['port'] = logging_socket.getsockname()[1]
		os.environ['jag_logging_port'] = str(sv_resources.cfg['logging']['port'])

		# create and launch the logger process
		logger_ctrl = multiprocessing.Process(target=logger_process, args=(sv_resources, logging_socket))
		logger_ctrl.start()

	print(_main_init, 'Creating and starting the server process... (2/7)')
	# Create a new process containing the main incoming connections listener
	server_ctrl = multiprocessing.Process(target=sock_server, args=(sv_resources,))
	print(_main_init, 'Created the process instructions, launching... (3/7)')
	# Initialize the created process
	# (It's not requred to create a new variable, it could be done in 1 line with .start() in the end)
	server_ctrl.start()

	print(_main_init, 'Launched the server process... (4/7)')




class JagRoute:
	def __init__(self, path=None, methods=None, cors=None, access_ctrl=None, cache_ctrl=None):
		self.path = path
		self.methods = methods

		self.cors = cors() if cors else jag_http_ents.CORSAllowance()
		self.cache_ctrl = cache_ctrl() if cache_ctrl else jag_http_ents.HTTPClientCacheControl()
		self.access_ctrl = access_ctrl if access_ctrl else jag_http_ents.AccessControl


	def __call__(self, func):
		self.func = func
		return self
		



class JagRoutingIndex:
	"""\
	The way routing in Jag works is similar to Flask:
	@JagRoute(path='/sex')
	def(request, response, services):
		pass

	Routes can be defined through any python file
	and must be located in the main body of the script.

	The @JagRoute() decorator transforms functions into classes.

	Each worker spawned by the server loads the said file with
	importlib. This is why it's very important to hide any executions
	in the main body of the file behind if __name__ == '__main__':
	(whenever any module/file is imported - everything inside gets executed)

	The worker then loops through every attribute of the imported file
	and checks if it's an instance of JagRoute class. 
	Each route gets written down for later use in HTTP sessions created
	by the same worker.
	"""
	def __init__(self, room_file):
		import importlib, sys

		module_file_path = room_file
		module_name = 'jag_custom_action'

		spec = importlib.util.spec_from_file_location(module_name, str(module_file_path))
		module = importlib.util.module_from_spec(spec)
		sys.modules[module_name] = module
		spec.loader.exec_module(module)

		self.custom_module = module
		self.routes = []
		self.default_route = None

	def find_routes(self):
		with DynamicGroupedText('Indexing Routes') as grouplog:
			for attr in dir(self.custom_module):
				route_obj = getattr(self.custom_module, attr)
				if isinstance(route_obj, JagRoute):
					# if path is not declared - that's a fallback route
					if not route_obj.path:
						grouplog.print('Registering default fallback route:', route_obj)
						self.default_route = route_obj
					else:
						# otherwise - get route info and write it down

						# convert methods to lowercase
						route_obj.methods = set([str(m).lower() for m in (route_obj.methods or [])]) or None
						route_obj.path = route_obj.path.lower()

						grouplog.print('Registering route:', route_obj)
						self.routes.append(route_obj)

	def match_route(self, requested_route, requested_method):
		requested_method = str(requested_method).lower()
		# Traverse through every declared route
		with DynamicGroupedText('Route lookup') as grouplog:
			# for allowed_path, allowed_methods, fnc in self.routes:
			for route_info in self.routes:
				# Check if requested path matches any of the declared paths
				grouplog.print('Validating route', 'Need:', requested_route, 'Allow:', route_info.path)
				if requested_route.startswith(route_info.path):
					# Check if requested method matches the declared method of the route
					# If route doesn't has a declared method - any method is allowed

					# Logic: If there are declared methods and requested method doesn't
					# match any of them - deny.
					grouplog.print('Validating methods:', 'Need:', requested_method, 'Allow:', route_info.methods)
					if route_info.methods and not requested_method in route_info.methods:
						grouplog.print('Method validation failed:', 'Need:', requested_method, 'Allow:', route_info.methods)
						# important todo: something that makes a little more sense than returning a string
						# maybe raising a custom Error ?
						return 'invalid_method'

					# Logic: If there are no declared methods - allow any method
					if not route_info.methods:
						grouplog.print('Route', route_info.path, 'doesnt restrict methods, allowing')
						return route_info

					# Logic: If allowed method matches requested method - proceed with execution
					if requested_method in route_info.methods:
						grouplog.print('Request method', requested_method, 'matches allowed methods', route_info.methods)
						return route_info

			# If no route was found - execute default function
			# Aka the function which was declared strictly like
			# @JagRoute()
			grouplog.print('Couldnt find a suitable route.', 'Requested route:', requested_route)
			return self.default_route




class JagServer(NestedProcessControl):
	"""\
	The root of the HTTP server.
	"""
	def __init__(self, launch_params):
		self.launch_params = JagHTTPServerResources(launch_params)
		self.routes = None
		self.threaded = not self.launch_params.cfg['multiprocessing']['enabled']

	def launch(self):
		if not self.threaded:
			self.server_process = multiprocessing.Process(target=server_process, args=(self.launch_params,))
			self.server_process.start()
			self.running = True
		else:
			self.server_process = threading.Thread(target=server_process, args=(self.launch_params,))
			self.server_process.start()
			self.running = True








