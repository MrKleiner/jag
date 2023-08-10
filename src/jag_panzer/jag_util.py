

def dict_pretty_print(d):
	return
	sex = '\n'
	for key in d:
		sex += f"""{('>' + str(key) + '<').ljust(30)} :: >{str(d[key])}<""" + '\n'

	print(sex)

def multireplace(src, replace_pairs):
	for replace_what, replace_with in replace_pairs:
		src = src.replace(replace_what, replace_with)
	return src


def clamp(num, tgt_min, tgt_max):
	return max(tgt_min, min(num, tgt_max))


def int_to_chunksize(i):
	return f"""{hex(i).lstrip('0x')}\r\n""".encode()



def get_current_ip():
	import socket
	return ([l for l in ([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] 
	if not ip.startswith("127.")][:1], [[(s.connect(('8.8.8.8', 53)), 
	s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, 
	socket.SOCK_DGRAM)]][0][1]]) if l][0][0])

