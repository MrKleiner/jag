import socket, threading, time, sys, hashlib, json, base64, struct, io, multiprocessing, os
from pathlib import Path
import traceback

# important todo: wat ?
# (this library simply has to be a proper package)
sys.path.append(str(Path(__file__).parent))

from base_room import base_room
import jag_util

from easy_timings.mstime import perftest

_main_init = '[root]'
_server_proc = '[Server Process]'



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
	"""precache python libraries"""
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
class server_info:
	"""
	Server info.
	This class contains the config itself,
	some preloaded python libraries,
	and other stuff
	"""
	def __init__(self, init_config=None):
		from mimes.mime_types_base import base_mimes
		from mimes.mime_types_base import base_mimes_signed
		from response_codes import codes as _rcodes

		from pathlib import Path
		import io
		import jag_util

		self.devtime = 0

		config = init_config or {}

		# root of the python package
		self.sysroot = Path(__file__).parent

		# extend python paths with included libs
		sys.path.append(str(self.sysroot / 'libs'))

		# mimes
		self.mimes = {
			'regular': base_mimes,
			'signed': base_mimes_signed,
		}

		# HTTP response codes
		self.response_codes = _rcodes

		# Reject document precache
		self.reject_precache = (self.sysroot / 'assets' / 'reject.html').read_bytes()


		#
		# Base config
		#
		self.cfg = {
			# Port to run the server on
			'port': 0,

			# Document root (where index.html is)
			'doc_root': None,

			# This path should point to a python file with "main()" function inside
			# If nothing is specified, then default room is created
			'room_file': None,

			# Could possibly be treated as bootleg anti-ddos/spam
			'max_connections': 0,

			# The amount of workers in the pool
			'pool_size': os.cpu_count()*2,

			# https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Server-Timing
			'enable_web_timing_api': False,

			# The name of the html file to serve when request path is '/'
			'root_index': None,
			'enable_indexes': True,
			'index_names': ['index.html'],
		} | config

		self.doc_root = Path(self.cfg['doc_root'])


		#
		# Directory Listing
		# 
		self.cfg['dir_listing'] = {
			'enabled': False,
			'dark_theme': False,
		} | (config.get('dir_listing') or {})



		# 
		# Advanced CDN serving
		# 
		self.cfg['static_cdn'] = {
			# Path to the static CDN
			# can point anywhere
			'path': None,
			# Relieve the filesystem stress by precaching items inside this folder
			# only useful if folder contains a big amount of small files
			'precache': True,
			# An array of paths relative to the root cdn path
			# to exclude from caching
			'cache_exclude': [],
			# Glob pattern for caching files, default to '*'
			'pattern': None,
			# Wether to trigger the callback function
			# when incoming request is trying to access the static CDN
			'skip_callback': True,
		} | (config.get('static_cdn') or {})

		self.cdn_path = None
		self.cdn_cache = {}

		if self.cfg['static_cdn']['path']:
			self.cdn_path = Path(self.cfg['static_cdn']['path'])
			self.precache_cdn()


		# 
		# Buffer sizes
		# 
		self.cfg['buffers'] = {
			# Max file size when serving a file through built-in server services
			# Default to 8mb
			'max_file_len': (1024**2)*8,

			# Max size of the header buffer
			# Default to 512kb
			'max_header_len': 1024*512,

			# Default size of a single chunk when streaming buffers
			# Default to 5mb
			'bufstream_chunk_len': (1024**2)*5,
		} | (config.get('buffers') or {})


	def reload_libs(self):
		# preload python libraries
		self.pylib = pylib_preload()






def sock_server(sv_cfg):
	# Preload resources n stuff
	print(_server_proc, 'Preloading resources... (4/7)')
	server_resources = server_info(sv_cfg)
	print(_server_proc, 'Binding server to a port... (5/7)')
	# Port to run the server on
	# port = 56817
	port = server_resources.cfg['port']
	# Create the Server object
	s = socket.socket()

	# Bind server to the specified port. 0 = Find the closest free port and run stuff on it
	# todo: is this really the only way to bind stuff to the current IP ?
	_get_ip_s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	_get_ip_s.connect(('8.8.8.8', 0))
	current_ip = _get_ip_s.getsockname()[0]
	s.bind(
		(current_ip, port)
	)

	# Basically launch the server
	# The number passed to this function identifies the max amount of simultaneous connections
	# If the amount of connections exceeds this limit -
	# connections become rejected till other ones are resolved (aka closed)
	# 0 = infinite
	s.listen(server_resources.cfg['max_connections'])

	print(_server_proc, 'Server listening on port (6/7)', s.getsockname()[1])

	# important todo: does this actually slow the shit down?
	# important todo: is it just me or this crashes the system ???!!?!??!?!?!?!?
	# important todo: this creates a bunch of threads as a side effect
	# important todo: Pickling is EXTREMELY slow and bad

	# Multiprocess pool automatically takes care of a bunch of stuff
	# But most importantly, it takes care of shadow processess left after collapsed rooms
	# (linux moment)

	# EXCEPT, process pool is garbage: It's a pool with a fixed amount of workers,
	# where tasks are distributed between them. Shit
	# EXCEPT, the amount of workes can be specified manually
	with multiprocessing.Pool(server_resources.cfg['pool_size']) as pool:
		print(_server_proc, 'Accepting connections... (7/7)')
		while True:
			print('Waiting for requests...')
			# conlog('Entering the main listen cycle which would spawn rooms upon incoming connection requests...', echo=_server_proc)
			# Try establishing connection, nothing below this line gets executed
			# until server receives a new connection
			conn, address = s.accept()
			# conlog('Got connection, spawning a room. Client info:', address, echo=_server_proc)
			# Create a basic room
			server_resources.devtime = time.time()
			pool.apply_async(base_room, (conn, address, server_resources))
			print('    Got request, forwarding...')
			# conlog('Spawned a room, continue accepting new connections', echo=_server_proc)
			# poot = multiprocessing.Process(target=base_room, args=(conn, address, server_resources,), daemon=True).start()
			# with perftest('      Forking...'):
			# 	multiprocessing.Process(target=base_room, args=(conn, address, server_resources,), daemon=True).start()
			# 	multiprocessing.Process(target=base_room, args=(conn, address, server_resources), daemon=True).start()
			# 	multiprocessing.Process(target=base_room, args=(conn, address, 'sex')).start()
			# 	pool.apply_async(base_room, (conn, address, server_resources))
			# 	pool.apply_async(base_room, (conn, address, server_resources))




def server_process(srv_params, stfu=False):
	print(_main_init, 'Creating and starting the server process... (1/7)')
	# Create a new process containing the main incoming connections listener
	server_ctrl = multiprocessing.Process(target=sock_server, args=(srv_params,))
	print(_main_init, 'Created the process instructions, attempting launch... (2/7)')
	# Initialize the created process
	# (It's not requred to create a new variable, it could be done in 1 line with .start() in the end)
	server_ctrl.start()

	print(_main_init, 'Launched the server process... (3/7)')




if __name__ == '__main__':
	server_params = {
		'doc_root': r'E:\!webdesign\jag',
		'port': 56817,
		'dir_listing': {
			'enabled': True,
		},
		# 'routes': _routes,
	}
	server_process(server_params)






