



def case_one(request, response, services):
	if request.method == 'post':
		collect_buf = request.srv_res.pylib.io.BytesIO()

		for chunk in request.read_body_stream():
			collect_buf.write(chunk)

		buf_as_bytes = collect_buf.getvalue()
		print('Collected buf length:', len(buf_as_bytes))
		print('Fuckshit', request.srv_res.pylib.hashlib.sha256(buf_as_bytes).hexdigest())
		request.reject(418)
	else:
		request.reject(423)



def case_two(request, response, services):
	request.reject(451)


def main(request, response, services):
	# Path = request.srv_res.pylib.Path

	decision = request.match_path({
		('/pootis', case_one),
		('/heavy/sandwich/dispenser', case_two),
	})

	if decision == False:
		services.serve_file(respect_range=False)




if __name__ == '__main__':
	from src.jag_panzer.server import server_process

	server_process({
		'doc_root': r'E:\!webdesign\jag',
		'port': 56817,
		'room_file': __file__,
		'dir_listing': {
			'enabled': False,
		}
	})