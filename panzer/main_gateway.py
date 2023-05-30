import socket, threading, time, sys, hashlib, json, base64, struct, io, multiprocessing
from base_room import base_room
from response_codes import codes as _rcodes
from pathlib import Path

from mimes.mime_types_base import base_mimes
from mimes.mime_types_base import base_mimes_signed

_main_init = '[root]'
_server_proc = '[Server Process]'

thisdir = Path(__file__).parent


_server_info = {
	'doc_root': Path(r'E:\!webdesign\jag'),
	'port': 56817,
	'cache': {
		'mimes': {
			'base_mimes': base_mimes,
			'base_mimes_signed': base_mimes_signed,
		},
		'pymodules': {
		},
		'assets':{
			'html': {
				'default_reject': (thisdir / 'assets' / 'reject.html').read_bytes(),
			},
		},
		'response_codes': _rcodes,
	},
}


def sock_server():
	print(_server_proc, 'Binding server to a port...')
	# Port to run the server on
	port = 56817
	# Create the Server object
	s = socket.socket()
	# Bind server to the specified port. 0 = Find the closest free port and run stuff on it
	s.bind(('192.168.0.10', port))

	# Basically launch the server
	# The number passed to this function identifies the max amount of simultaneous connections
	# If the amount of connections exceeds this limit - connections become rejected till other ones are resolved (aka closed)
	# 0 = infinite
	s.listen(0)

	print(_server_proc, 'Server listening on port', s.getsockname()[1])

	# important todo: does this actually slow the shit down?
	# important todo: is it just me or this crashes the system ???!!?!??!?!?!?!?
	# important todo: this creates a bunch of threads as a side effect
	
	# Multiprocess pool automatically takes care of a bunch of stuff
	# But most importantly, it takes care of shadow processess left after collapsed rooms
	with multiprocessing.Pool() as pool:
		while True:
			print(_server_proc, 'Entering the main listen cycle which would spawn rooms upon incoming connection requests...')
			# Try establishing connection, nothing below this line would get executed
			# until server receives a new connection
			conn, address = s.accept()
			print(_server_proc, 'Got connection, spawning a room. Client info:', address)

			# Create a basic room
			pool.apply_async(base_room, (conn, address, _server_info))

			print(_server_proc, 'Spawned a room, continue accepting new connections')



if __name__ == '__main__':
	print(_main_init, 'Creating and starting the server process...')
	# Create a new process containing the main incoming connections listener
	server_ctrl = multiprocessing.Process(target=sock_server)
	print(_main_init, 'Created the process instructions, trying to launch the process...')
	# Initialize the created process
	# (It's not requred to create a new variable, it could be done in 1 line with .start() in the end)
	server_ctrl.start()

	print(_main_init, 'Launched the server process...')















