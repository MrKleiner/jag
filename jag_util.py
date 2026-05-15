import traceback
import io




RECV_BUF_FLOOR = 512




def str_exception(err):
	try:
		return ''.join(
			traceback.format_exception(
				type(err),
				err,
				err.__traceback__
			)
		)
	except Exception as e:
		print(e)


def print_exception(err):
	try:
		print(
			''.join(
				traceback.format_exception(
					type(err),
					err,
					err.__traceback__
				)
			)
		)
	except Exception as e:
		print(e)


def print_exception_framed(err):
	try:
		formatted = ''.join(
			traceback.format_exception(
				type(err),
				err,
				err.__traceback__
			)
		)

		exception_lines = []

		for line in formatted.split('\n'):
			for chunk in [line[i:i+120] for i in range(0, len(line), 120)]:
				exception_lines.append(chunk)

		max_len = 0
		for idx, line in enumerate(exception_lines):
			if len(line) > max_len:
				max_len = len(line)

		print_lines = [
			'+' + ('-' * (max_len + 3 + 4 - 2)) + '+',
		]

		for idx, line in enumerate(exception_lines):
			print_lines.append(
				'| ' + line.ljust(max_len + 3) + ' |'
			)

		print_lines.append(
			'+' + ('-' * (max_len + 3 + 4 - 2)) + '+'
		)

		print(
			'\n'.join(print_lines)
		)

	except Exception as e:
		print_exception(e)


def clamp_num(num, tgt_min, tgt_max):
	return max(tgt_min, min(num, tgt_max))


def aligned_recv(skt_con, bufsize, chunk_size=8192):
	# Shouldn't this print a warning or something ?
	if bufsize <= 0:
		return b''

	# Creating an io.BytesIO buffer to receive 2 bytes
	# is MUCH slower than simple concatenating (b'' + ...)
	# Through tests it was determined that there's no need to
	# create a buffer for receiving less than 512 bytes.
	# todo: Lower the number a little bit just to be sure?
	if bufsize < RECV_BUF_FLOOR:
		buf = b''
		# print('Need to receive:', bufsize)
		while True:
			# todo: raise a warning when the result is actually longer
			# than anticipated
			if len(buf) >= bufsize:
				return buf

			data = skt_con.recv(
				clamp_num(chunk_size, 1, bufsize - len(buf))
			)

			if not data:
				raise ConnectionError('Connection closed')

			buf += data
	else:
		buf = io.BytesIO()
		while True:
			if buf.tell() >= bufsize:
				return buf.getvalue()

			data = skt_con.recv(
				clamp_num(chunk_size, 1, bufsize - buf.tell())
			)

			if not data:
				raise ConnectionError('Connection closed')

			buf.write(data)

		buf = buf.getvalue()

	return buf




