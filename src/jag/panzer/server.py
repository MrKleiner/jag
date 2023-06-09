import socket, threading, time, sys, hashlib, json, base64, struct, io, multiprocessing
from pathlib import Path
import traceback

# important todo: wat ?
# (this library simply has to be a proper package)
sys.path.append(str(Path(__file__).parent))

from base_room import base_room
import jag_util

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
	def __init__(self, config=None):
		from mimes.mime_types_base import base_mimes
		from mimes.mime_types_base import base_mimes_signed
		from response_codes import codes as _rcodes

		from pathlib import Path
		import io
		import jag_util

		config = config or {}

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

		# Base config
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

			# The name of the html file to serve when request path is '/'
			'root_index': None,
			'enable_indexes': True,
			'index_names': ['index.html'],

			# The size of a single chunk when streaming content in HTTP chunks
			'chunk_stream_piece_size': (1024*1024)*10,
		} | config

		self.doc_root = Path(self.cfg['doc_root'])

		# Directory Listing
		self.cfg['dir_listing'] = {
			'enabled': True,
			'dark_theme': False,
		} | (config.get('dir_listing') or {})

		if self.cfg['dir_listing']['enabled']:
			from dir_list import dirlist
			self.list_dir = dirlist(self)

		# Advanced CDN serving
		self.cfg['static_cdn'] = {
			'max_buffered_size': (1024*1024)*10,
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

	def precache_cdn(self):
		for file in self.cdn_path.rglob(self.cfg['static_cdn']['pattern'] or '*'):
			self.cdn_cache[file.relative_to(self.cdn_path).as_posix()] = \
				io.BytesIO(file.read_bytes())

		print(
			_server_proc,
			'precached CDN',
			jag_util.dict_pretty_print(self.cdn_cache)
		)

	def reload_libs(self):
		import time
		ded = time.time()
		# preload python libraries
		self.pylib = pylib_preload()
		print('Preloaded libs in', (time.time() - ded)*1000)



def sock_server(sv_cfg):
	# Preload resources n stuff
	print(_server_proc, 'Preloading resources...')
	server_resources = server_info(sv_cfg)
	print(_server_proc, 'Binding server to a port...')
	# Port to run the server on
	# port = 56817
	port = server_resources.cfg['port']
	# Create the Server object
	s = socket.socket()
	# Bind server to the specified port. 0 = Find the closest free port and run stuff on it
	s.bind(
		('192.168.0.10', port)
	)

	# Basically launch the server
	# The number passed to this function identifies the max amount of simultaneous connections
	# If the amount of connections exceeds this limit -
	# connections become rejected till other ones are resolved (aka closed)
	# 0 = infinite
	s.listen(server_resources.cfg['max_connections'])

	print(_server_proc, 'Server listening on port', s.getsockname()[1])

	# important todo: does this actually slow the shit down?
	# important todo: is it just me or this crashes the system ???!!?!??!?!?!?!?
	# important todo: this creates a bunch of threads as a side effect
	# important todo: Pickling is EXTREMELY slow and bad

	# Multiprocess pool automatically takes care of a bunch of stuff
	# But most importantly, it takes care of shadow processess left after collapsed rooms
	# (linux moment)
	with multiprocessing.Pool() as pool:
		while True:
			print(_server_proc, 'Entering the main listen cycle which would spawn rooms upon incoming connection requests...')
			# Try establishing connection, nothing below this line gets executed
			# until server receives a new connection
			conn, address = s.accept()
			print(_server_proc, 'Got connection, spawning a room. Client info:', address)
			# Create a basic room
			pool.apply_async(base_room, (conn, address, server_resources))

			print(_server_proc, 'Spawned a room, continue accepting new connections')


def server_process(srv_params, stfu=False):
	print(_main_init, 'Creating and starting the server process...')
	# Create a new process containing the main incoming connections listener
	server_ctrl = multiprocessing.Process(target=sock_server, args=(srv_params,))
	print(_main_init, 'Created the process instructions, attempting launch...')
	# Initialize the created process
	# (It's not requred to create a new variable, it could be done in 1 line with .start() in the end)
	server_ctrl.start()

	print(_main_init, 'Launched the server process...')




if __name__ == '__main__':
	server_params = {
		'doc_root': r'E:\!webdesign\jag',
		'port': 56817,
		'dir_listing': {
			'enabled': True,
		}
	}
	server_process(server_params)






