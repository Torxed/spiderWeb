import types
from socket import *
from base64 import b64encode
from hashlib import sha1
from json import loads, dumps
from struct import pack, unpack
from datetime import date, datetime
try:
	from select import epoll, EPOLLIN
except:
	""" #!if windows
	Create a epoll() implementation that simulates the epoll() behavior.
	This so that the rest of the code doesn't need to worry weither or not epoll() exists.
	"""
	import select
	EPOLLIN = None
	class epoll():
		def __init__(self):
			self.sockets = {}
			self.monitoring = {}

		def unregister(self, fileno, *args, **kwargs):
			try:
				del(self.monitoring[fileno])
			except:
				pass

		def register(self, fileno, *args, **kwargs):
			self.monitoring[fileno] = True

		def poll(self, timeout=0.5, *args, **kwargs):
			try:
				return [[fileno, 1] for fileno in select.select(list(self.monitoring.keys()), [], [], timeout)[0]]
			except OSError:
				return []

try:
	if not 'LEVEL' in __builtins__.__dict__: __builtins__.__dict__['LEVEL'] = 1
except:
	if not 'LEVEL' in __builtins__: __builtins__['LEVEL'] = 1

def log(*args, **kwargs):
	print(' '.join([str(x) for x in args]))

class PacketIncomplete(Exception):
	def __init__(self, message, errors):

		# Call the base class constructor with the parameters it needs
		super().__init__(message)

		# Now for your custom code...
		self.errors = errors

class Events():
	SERVER_ACCEPT = 0b10000000
	SERVER_CLOSE = 0b10000001
	SERVER_RESTART = 0b00000010

	CLIENT_DATA = 0b01000000
	CLIENT_REQUEST = 0b01000001
	CLIENT_RESPONSE_DATA = 0b01000010
	CLIENT_UPGRADED = 0b01000011
	CLIENT_UPGRADE_ISSUE = 0b01000100
	CLIENT_URL_ROUTED = 0b01000101

	WS_CLIENT_DATA = 0b11000000
	WS_CLIENT_REQUEST = 0b11000001
	WS_CLIENT_COMPLETE_FRAME = 0b11000010
	WS_CLIENT_INCOMPLETE_FRAME = 0b11000011
	WS_CLIENT_ROUTING = 0b11000100
	WS_CLIENT_ROUTED = 0b11000101
	WS_CLIENT_RESPONSE = 0b11000110

	NOT_YET_IMPLEMENTED = 0b00000000

def json_serial(obj):
	if isinstance(obj, (datetime, date)):
		return obj.isoformat()
	elif type(obj) is bytes:
		return obj.decode('UTF-8')
	elif getattr(obj, "__dump__", None): #hasattr(obj, '__dump__'):
		return obj.__dump__()
	else:
		return str(obj)

	raise TypeError('Type {} is not serializable: {}'.format(type(obj), obj))

def list_to_dict(_list_):
	# TODO: Verify that the length is dividable with 2.
	a, b = _list_[:len(_list_)//2], _list_[len(_list_)//2:]
	result = {}
	for index, item in enumerate(a):
		result[item] = b[index]
	return result

class WS_ROUTE():
	def __init__(self, route, func=None):
		self.route = route
		self.func = func

	def router(self, f, *args, **kwargs):
		self.func = f

class WebSocket():
	def __init__(self):
		self.routes = {}
		self.loaded_apis = {}

	def log(self, *args, **kwargs):
		print(' '.join([str(x) for x in args]))

	def route(self, URL, *args, **kwargs):
		self.routes[URL] = WS_ROUTE(URL)
		return self.routes[URL].router

	def WS_CLIENT_IDENTITY(self, request):
		self.log=request.CLIENT_IDENTITY.server.log
		return WS_CLIENT_IDENTITY(request, server=self)

#	def find_final_module_path(path, data):
#		if '_module' in data:
#			if data['_module'] in data and '_module' in data[data['_module']] and isdir(f"{path}/{data['_module']}"):
#				return find_final_module_path(path=f"{path}/{data['_module']}", data=data[data['_module']])
#			elif isfile(f"{path}/{data['_module']}.py"):
#				return {'path' : f"{path}/{data['_module']}.py", 'data' : data, 'api_path' : ':'.join(f"{path}/{data['_module']}"[len('./api_modules/'):].split('/'))}

	def find_final_module_path(path, frame):
		full_path = f"{path}/{frame.data['_module']}.py"
		if isfile(full_path):
			return full_path

	def importer(path):
		old_version = False
		self.log(f'Request to import "{path}"', level=6, origin='importer')
		if path not in self.loaded_apis:
			## https://justus.science/blog/2015/04/19/sys.modules-is-dangerous.html
			try:
				self.log(f'Loading API module: {path}', level=4, origin='importer')
				spec = importlib.util.spec_from_file_location(path, path)
				self.loaded_apis[path] = importlib.util.module_from_spec(spec)
				spec.loader.exec_module(self.loaded_apis[path])
				sys.modules[path] = self.loaded_apis[path]
			except (SyntaxError, ModuleNotFoundError) as e:
				self.log(f'Failed to load API module ({e}): {path}', level=2, origin='importer')
				return None
		else:
			try:
				raise SyntaxError('https://github.com/Torxed/ADderall/issues/11')
			except SyntaxError as e:
				old_version = True

		return old_version, self.loaded_apis[f'{path}']

	def route_parser_func(self, frame):
		if type(frame.data) is not dict or '_module' not in frame.data:
			self.log(f'Invalid request sent, missing _module in JSON data: {str(frame.data)[:200]}', source='WebSocket.route_parser_func(WS_FRAME)')
			return

		if frame.data['_module'] in self.routes:
			response = self.routes[frame.data['_module']].func(frame)
			yield (Events.WS_CLIENT_RESPONSE, response)
		else:
			## TODO: Add path security!
			module_to_load = self.find_final_module_path('./api_modules', frame)
			if(module_to_load):
				import_result = importer(module_to_load)
				if import_result:
					old_version, handle = import_result

					# Just keep track if we're executing the new code or the old, for logging purposes only
					if not old_version:
						self.log(f'Calling {handle}.parser.process(client, data, headers, fileno, addr, *args, **kwargs)', source='WebSocket.route_parser_func(WS_FRAME)')
					else:
						self.log(f'Calling old {handle}.parser.process(client, data, headers, fileno, addr, *args, **kwargs)', source='WebSocket.route_parser_func(WS_FRAME)')

					try:
						response = modules[module_to_load].parser.process(frame)
						if response:
							if isinstance(response, Iterator):
								for item in response:
									yield {
										**item,
										'_uid' : data['_uid'] if '_uid' in data else None,
										'_modules' : module_to_load['api_path']
									}
							else:
								yield {
									**response,
									'_uid' : data['_uid'] if '_uid' in data else None,
									'_modules' : module_to_load['api_path']
								}
					except BaseException as e:
						exc_type, exc_obj, exc_tb = sys.exc_info()
						fname = path_split(exc_tb.tb_frame.f_code.co_filename)[1]
						self.log(f'Module error in {fname}@{exc_tb.tb_lineno}: {e} ', source='WebSocket.route_parser_func(WS_FRAME)')
						self.log(traceback.format_exc(), level=2, origin='pre_parser', function='parse')
			else:
				self.log(f'Invalid data, trying to load a inexisting module: {data["_module"]} ({str(data)[:200]})', level=3, origin='pre_parser', function='parse')	


	def post_process_frame(self, frame):
		try:
			frame.data = loads(frame.data.decode('UTF-8'))
			for event, state in self.route_parser_func(frame):
				yield (event, state)
		except UnicodeDecodeError:
			self.log('[ERROR] UnicodeDecodeError:', frame.data, source='WebSocket.post_process_frame(WS_FRAME)')
			return None
		except Exception as e:
			exc_type, exc_obj, exc_tb = sys.exc_info()
			fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
			self.log(f'JSON error loading data {fname}@{exc_tb.tb_lineno}:', frame.data, source='WebSocket.post_process_frame(WS_FRAME)')
			self.log(traceback.format_exc(), level=3)
			return None

class WS_CLIENT_IDENTITY():
	def __init__(self, request, server=None):
		if not server: server = request.CLIENT_IDENTITY.server
		self.server = server
		self.socket = request.CLIENT_IDENTITY.socket
		self.fileno = request.CLIENT_IDENTITY.fileno
		self.address = request.CLIENT_IDENTITY.address
		self.keep_alive = request.CLIENT_IDENTITY.keep_alive
		self.buffer_size = 8192
		self.closing = False

		self.buffer = request.CLIENT_IDENTITY.buffer # Take over the buffer
		self.on_close = request.CLIENT_IDENTITY.on_close

	def upgrade(self, request):
		self.server.log(f'Performing upgrade() response for: {self}', level=5, source='WS_CLIENT_IDENTITY.upgrade()')
		self.keep_alive = True

		magic_key = request.request_headers[b'sec-websocket-key'] + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
		magic_hash = sha1(magic_key).digest()

		resp = b''
		resp += b'HTTP/1.1 101 Switching protocols\r\n'
		resp += b'Upgrade: websocket\r\n'
		resp += b'Connection: Upgrade\r\n'
		resp += b'Sec-WebSocket-Accept: ' + b64encode(magic_hash) + b'\r\n'
		resp += b'\r\n'

		self.socket.send(resp)
		self.buffer = b''

		self.server.log(f'{self}\'s upgrade response is sent.', level=5, source='WS_CLIENT_IDENTITY.upgrade()')

	def close(self):
		if not self.closing:
			self.closing = True
			self.on_close(self)

	def on_close(self, *args, **kwargs):
		if not self.closing:
			self.server.on_close_func(self)

	def poll(self, timeout=0.2, force_recieve=False):
		"""
		@force_recieve: If the caller knows there's data, we can override
		the polling event and skip straight to data recieving.
		"""
		if force_recieve or list(self.server.poll(timeout, fileno=self.fileno)):
			try:
				d = self.socket.recv(self.buffer_size)
			except: # There's to many errors that can be thrown here for differnet reasons, SSL, OSError, Connection errors etc.
			        # They all mean the same thing, things broke and the client couldn't deliver data accordingly so eject.
				d = ''

			if len(d) == 0:
				return self.on_close(self)

			self.buffer += d
			yield (Events.WS_CLIENT_DATA, len(self.buffer))

	def send(self, data):
		self.socket.send(data)

	def build_request(self):
		yield (Events.CLIENT_REQUEST, WS_FRAME(self))

	def has_data(self):
		if self.closing: return False
		return True if len(self.buffer) else False

	def __repr__(self):
		return f'<spiderWeb.WS_CLIENT_IDENTITY @ {self.address}>'

class WS_FRAME():
	def __init__(self, CLIENT_IDENTITY):
		self.CLIENT_IDENTITY = CLIENT_IDENTITY

	def parse(self):
		## == Some initial checks, to see if we got all the data, the opcode etc.
		self.data_index = 0
		flags = '{0:0>8b}'.format(unpack('B', bytes([self.CLIENT_IDENTITY.buffer[self.data_index]]))[0])
		fin, rsv1, rsv2, rsv3 = [True if x == '1' else False for x in flags[0:4]]
		opcode = int(flags[4:8], 2)

		self.flags = {'fin' : fin, 'rsv1' : rsv1, 'rsv2' : rsv2, 'rsv3' : rsv3, 'mask' : None}
		self.opcode = opcode
		
		#if fragmented in (None, 0, False):
		#	if self.opcode != 0 and not self.flags['fin']:
		#		self.fragmented = True
		#	elif self.flags['fin']:
		#		self.fragmented = False
		#else:
		#	self.fragmented = fragmented

		self.complete_frame = False

		self.payload_len = 0
		self.mask_key = None
		self.data = b''
		self.raw_data = self.CLIENT_IDENTITY.buffer
		#self.carryOver = b''
		self.CLIENT_IDENTITY.server.log('Flags:', self.flags, level=10, origin='spiderWeb', function='ws_packet')
		self.CLIENT_IDENTITY.server.log('opcode:', self.opcode, level=10, origin='spiderWeb', function='ws_packet')
		
		## == We skip the first 0 index because data[index 0] is the [fin,rsv1,rsv2,rsv3,opcode] byte.
		self.data_index += 1

		## ------- Begin parsing

		if len(self.raw_data) >= 2 and self.payload_len == 0:
			## == Check the initial length of the payload.
			##    Websockets have 3 conditional payload lengths:
			##	  * https://stackoverflow.com/questions/18271598/how-to-work-out-payload-size-from-html5-websocket
			self.payload_len = unpack('B', bytes([self.raw_data[self.data_index]]))[0]
			self.payload_len = '{0:0>8b}'.format(self.payload_len)

			self.flags['mask'], self.payload_len = (True if self.payload_len[0] == '1' else False), int('{:0>8}'.format(self.payload_len[1:]), 2)
			self.data_index += 1

		# B = 1
		# H = 2
		# I = 4
		# Q = 8

		## == TODO: When we've successfully established the payload length,
		##          make sure we actually have recieved that much data.
		##          (for instance, recv(1024) might get the header, but not the full length)

		## == CONDITION 1: The length is less than 126 - Which means whatever length this is, is the actual payload length.
		if self.payload_len < 126:
			self.CLIENT_IDENTITY.server.log('Len:', self.payload_len, level=10, origin='spiderWeb', function='ws_packet')

		## == CONDITION 2: Length is 126, which means the next [2 bytes] are the length.
		elif self.payload_len == 126 and len(self.raw_data) >= self.data_index+2:
			self.payload_len = unpack('>H', self.raw_data[self.data_index:self.data_index+2])[0]
			self.data_index += 2
			self.CLIENT_IDENTITY.server.log('Large payload:', self.payload_len, level=10, origin='spiderWeb', function='ws_packet')

		## == Condition 3: Length is 127, which means the next [8] bytes are the length.
		elif self.payload_len == 127 and len(self.raw_data) >= self.data_index+2:
			self.payload_len = unpack('>Q', self.raw_data[self.data_index:self.data_index+8])[0]
			self.data_index += 8
			self.CLIENT_IDENTITY.server.log('Huge payload:', self.payload_len, level=10, origin='spiderWeb', function='ws_packet')

		if len(self.raw_data) < self.payload_len:
			self.complete_frame = False
			return

		## == We try to see if the package is XOR:ed (mask=True) and data length is larger than 4.
		if self.flags['mask'] and len(self.raw_data) >= self.data_index+4:
			#mask_key = unpack('I', ws[parsed_index:parsed_index+4])[0]
			self.mask_key = self.raw_data[self.data_index:self.data_index+4]
			self.CLIENT_IDENTITY.server.log('Mask key:', self.mask_key, level=10, origin='spiderWeb', function='ws_packet')
			self.data_index += 4

		if self.flags['mask']:
			self.data = b''
			self.CLIENT_IDENTITY.server.log('[XOR::Data]:', self.raw_data[self.data_index:self.data_index+self.payload_len], level=10, origin='spiderWeb', function='ws_packet')
			for index, c in enumerate(self.raw_data[self.data_index:self.data_index+self.payload_len]):
				self.data += bytes([c ^ self.mask_key[(index%4)]])
			self.CLIENT_IDENTITY.server.log('[   ::Data]:', self.data, level=9, origin='spiderWeb', function='ws_packet')
			self.data_index += self.payload_len

			self.CLIENT_IDENTITY.buffer = self.CLIENT_IDENTITY.buffer[self.data_index:]


			if self.data == b'PING':
				#self.ws_send(b'Pong') #?
				self.data = None
				return

			print('Data:', self.data)
			if len(self.data) < self.payload_len:
				self.complete_frame = False
				## Ok so, TODO:
				#  This fucking code shouldn't need to be here...
				#  I don't know WHY handler.poll() in core.py doesn't work as it should,
				#  but it should return a fileno+event when there's more data to the payload.
				#  But for whatever reason, handler.poll() returms empty even tho there's more data
				#  to be collected for this websocket-packet.. and doing recv() again does actually
				#  return more data - epoll() just don't know about it for some reason.
				#  So the only way to do this, is to raise PacketIncomplete() and let outselves
				#  trigger another recv() manually from within this parse-session.
				#  The main issue with this tho, is that someone could send a fake length + not send data.
				#  Effectively blocking this entire application.. I don't like this one bit..
				#  But for now, fuck it, just keep the project going and we'll figure out why later!
				#  (FAMOUSE LAST WORDS)
				#raise PacketIncomplete("Incomplete packet.", (self.payload_len, len(self.carryOver)))
			else:
				self.complete_frame = True
				if self.flags['fin']:
					print('Got finished data')
					#if self.fragmented:
					#	self.fragmented = False # TODO: needed?
					#else:
					#	self.convert_to_json() # Also used internally for normal data
					yield (Events.WS_CLIENT_COMPLETE_FRAME, self)

					for subevent, entity in self.CLIENT_IDENTITY.server.post_process_frame(self):
						#yield (Events.WS_CLIENT_ROUTING, )
						yield subevent, entity
				else:
					print('Got unfinished data')
					yield (Events.WS_CLIENT_INCOMPLETE_FRAME, self)

class ws_packet():
	def __init__(self, data, data_index=0, fragmented=None):
		## == Some initial checks, to see if we got all the data, the opcode etc.
		flags = '{0:0>8b}'.format(unpack('B', bytes([data[data_index]]))[0])
		fin, rsv1, rsv2, rsv3 = [True if x == '1' else False for x in flags[0:4]]
		opcode = int(flags[4:8], 2)

		self.flags = {'fin' : fin, 'rsv1' : rsv1, 'rsv2' : rsv2, 'rsv3' : rsv3, 'mask' : None}
		self.opcode = opcode
		
		if fragmented in (None, 0, False):
			if self.opcode != 0 and not self.flags['fin']:
				self.fragmented = True
			elif self.flags['fin']:
				self.fragmented = False
		else:
			self.fragmented = fragmented

		self.complete_frame = False

		self.payload_len = 0
		self.mask_key = None
		self.data = b''
		self.raw_data = data
		#self.carryOver = b''
		log('Flags:', self.flags, level=10, origin='spiderWeb', function='ws_packet')
		log('opcode:', self.opcode, level=10, origin='spiderWeb', function='ws_packet')
		
		## == We skip the first 0 index because data[index 0] is the [fin,rsv1,rsv2,rsv3,opcode] byte.
		self.data_index = data_index + 1

		## ------- Begin parsing
		
		if len(data) >= 2 and self.payload_len == 0:
			## == Check the initial length of the payload.
			##    Websockets have 3 conditional payload lengths:
			##	  * https://stackoverflow.com/questions/18271598/how-to-work-out-payload-size-from-html5-websocket
			self.payload_len = unpack('B', bytes([data[self.data_index]]))[0]
			self.payload_len = '{0:0>8b}'.format(self.payload_len)

			self.flags['mask'], self.payload_len = (True if self.payload_len[0] == '1' else False), int('{:0>8}'.format(self.payload_len[1:]), 2)
			self.data_index += 1

		# B = 1
		# H = 2
		# I = 4
		# Q = 8

		## == TODO: When we've successfully established the payload length,
		##          make sure we actually have recieved that much data.
		##          (for instance, recv(1024) might get the header, but not the full length)

		## == CONDITION 1: The length is less than 126 - Which means whatever length this is, is the actual payload length.
		if self.payload_len < 126:
			log('Len:', self.payload_len, level=10, origin='spiderWeb', function='ws_packet')

		## == CONDITION 2: Length is 126, which means the next [2 bytes] are the length.
		elif self.payload_len == 126 and len(data) >= self.data_index+2:
			self.payload_len = unpack('>H', data[self.data_index:self.data_index+2])[0]
			self.data_index += 2
			log('Large payload:', self.payload_len, level=10, origin='spiderWeb', function='ws_packet')

		## == Condition 3: Length is 127, which means the next [8] bytes are the length.
		elif self.payload_len == 127 and len(data) >= self.data_index+2:
			self.payload_len = unpack('>Q', data[self.data_index:self.data_index+8])[0]
			self.data_index += 8
			log('Huge payload:', self.payload_len, level=10, origin='spiderWeb', function='ws_packet')

		if len(data) < self.payload_len:
			self.complete_frame = False
			return

		## == We try to see if the package is XOR:ed (mask=True) and data length is larger than 4.
		if self.flags['mask'] and len(data) >= self.data_index+4:
			#mask_key = unpack('I', ws[parsed_index:parsed_index+4])[0]
			self.mask_key = data[self.data_index:self.data_index+4]
			log('Mask key:', self.mask_key, level=10, origin='spiderWeb', function='ws_packet')
			self.data_index += 4

		if self.flags['mask']:
			self.data = b''
			log('[XOR::Data]:', data[self.data_index:self.data_index+self.payload_len], level=10, origin='spiderWeb', function='ws_packet')
			for index, c in enumerate(data[self.data_index:self.data_index+self.payload_len]):
				self.data += bytes([c ^ self.mask_key[(index%4)]])
			log('[   ::Data]:', self.data, level=9, origin='spiderWeb', function='ws_packet')
			self.data_index += self.payload_len

			if self.data == b'PING':
				#self.ws_send(b'Pong') #?
				self.data = None
				return

			if len(self.data) < self.payload_len:
				self.complete_frame = False
				## Ok so, TODO:
				#  This fucking code shouldn't need to be here...
				#  I don't know WHY handler.poll() in core.py doesn't work as it should,
				#  but it should return a fileno+event when there's more data to the payload.
				#  But for whatever reason, handler.poll() returms empty even tho there's more data
				#  to be collected for this websocket-packet.. and doing recv() again does actually
				#  return more data - epoll() just don't know about it for some reason.
				#  So the only way to do this, is to raise PacketIncomplete() and let outselves
				#  trigger another recv() manually from within this parse-session.
				#  The main issue with this tho, is that someone could send a fake length + not send data.
				#  Effectively blocking this entire application.. I don't like this one bit..
				#  But for now, fuck it, just keep the project going and we'll figure out why later!
				#  (FAMOUSE LAST WORDS)
				#raise PacketIncomplete("Incomplete packet.", (self.payload_len, len(self.carryOver)))
			else:
				self.complete_frame = True
				if self.flags['fin']:
					if self.fragmented:
						self.fragmented = False # TODO: needed?
					else:
						self.convert_to_json() # Also used internally for normal data

	def __enter__(self):
		return self

	def __exit__(self):
		pass

	def getRemainder(self):
		if not self.complete_frame:
			index = self.data_index = 0
		elif self.fragmented or self.flags['fin']:
			index = self.data_index
			self.data_index = 0
		else:
			index = self.data_index

		return self.raw_data[index:]

	def convert_to_json(self):
		try:
			self.data = loads(self.data.decode('UTF-8'))
		except UnicodeDecodeError:
			log('[ERROR] UnicodeDecodeError:', self.data, level=2, origin='spiderWeb', function='ws_packet')
			self.data = b''
			return False
		except Exception as e:
			log('Could not JSON encode the data:', level=3, origin='spiderWeb', function='ws_packet')
			log(e, level=3)
			raise ValueError("Could not parse the data as JSON: {} ... {}".format(self.data[:40], self.data[-40:]), e)

class upgrader():
	def __init__(self, parsers):
		self.parsers = parsers

	def upgrade(self, client, headers, data):
		log(f'Handling upgrade request from: {client}', level=5, origin='spiderWeb', function='upgrader.upgrade()')
		client.keep_alive = True

		init_headers = headers.copy()
		magic_key = headers[b'sec-websocket-key'] + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
		hash = sha1(magic_key).digest()

		resp = b''
		resp += b'HTTP/1.1 101 Switching protocols\r\n'
		resp += b'Upgrade: websocket\r\n'
		resp += b'Connection: Upgrade\r\n'
		resp += b'Sec-WebSocket-Accept: ' + b64encode(hash) + b'\r\n'
		resp += b'\r\n'

		client.send(resp)

		c = ws_client(client.socket, client.info['addr'], data, self.parsers)
		c.state = 'WEBSOCK'

		log(f'{client} has been upgraded', level=5, origin='spiderWeb', function='upgrader.upgrade()')
		return c

class ws_client():
	def __init__(self, sock, addr, data=b'', parsers={}):
		self.sock = sock
		self.addr = addr
		self.state = 'HTTP'
		self.data = data
		self.closed = False
		self.keep_alive = True
		self.upgraded = False

		self.fragments = []
		self.fragment_indexer = 0

		self.init_headers = {}

		#self.ws_packet = {'flags' : {'fin' : None, 'rsv1' : None, 'rsv2' : None, 'rsv3' : None, 'mask' : None},
		#		'opcode' : None,
		#		'payload_len' : 0,
		#		'mask_key' : None}
		#self.ws_index = 0

		self.headers, self.payload = None, None
		self.parsers = parsers

	def http_parse(self, d):
		if len(d) <= 0:
			return {}, b''
		headers = {}
		header, payload = d.split(b'\r\n\r\n',1)
		rows = header.split(b'\r\n')
		headers[b'REQUEST'] = rows[0].split(b' ',2)[1]

		for row in rows[1:]:
			key, val = row.split(b':',1)
			headers[key.strip(b' \\;,.\r\n')] = val.strip(b' \\;,.\r\n')
		return headers, payload

	def websock_parse(self):
		## TODO: Large data streams could end up clogging the pipepine for other clients.
		
		while 1:
			if len(self.data) <= 0:
				break # No more data here

			log('[Parsing packet]:', self.data[:100], level=10, origin='spiderWeb', function='websock_parse')

			## == Set up a ws_packet() based on all the data the client has sent us.
			packet = ws_packet(self.data, self.fragment_indexer, fragmented=len(self.fragments))

			self.data = packet.getRemainder()
			self.fragment_indexer = packet.data_index

			if packet.complete_frame:
				if packet.fragmented and not packet.flags['fin']:
					self.fragments.append(packet.data)
				elif not packet.fragmented and packet.flags['fin'] and len(self.fragments):
					self.fragments.append(packet.data)
					packet.data = b''.join(self.fragments)
					self.fragments = []
					packet.convert_to_json()
			else:
				break

			## == If we've recieved all the data, set the ws_client() internal data to
			##    any remainder the ws_packet() might have since the client might have sent
			##    two packets in one transfer, the next loop we'll set up a new ws_packet() with the remainder.

			if packet.flags['fin'] and packet.complete_frame and packet.data and not packet.fragmented:
				#if packet.data == b'':
				#	continue

				## == Call all our parsers and yield any data they have.
				for parser in self.parsers:
					handle = self.parsers[parser].parse(self, packet.data, self.headers, self.sock.fileno(), self.addr)
					if isinstance(handle, types.GeneratorType):
						for response in handle:
							yield response
					else:
						yield handle

			else:
				## == Still waiting for more data to arrive.
				break

	def send(self, data, *args, **kwargs):
		self.ws_send(data, *args, **kwargs)

	def ws_send(self, data, SPLIT=False):
		log('[Structuring a packet]', level=5, origin='spiderWeb', function='ws_send')

		if type(data) == dict:
			data = dumps(data, default=json_serial)
		if type(data) != bytes:
			data = bytes(str(data), 'UTF-8')

		if SPLIT: data = [data[0+i:SPLIT+i] for i in range(0, len(data), SPLIT)] # Might get in trouble if splitting to 126 or 127. TODO: investigate.
		else: data = [data]

		for index, segment in enumerate(data):
			packet = b''
			## Add the flags + opcode (0 == continuation frame, 1 == text, 2 == binary, 8 == con close, 9 == ping, A == pong)
			last_segment = True if index == len(data)-1 else False
			fin, rsv1, rsv2, rsv3, opcode = (b'1' if last_segment else b'0'), b'0', b'0', b'0', bytes('{:0>4}'.format('1' if last_segment else '0'), 'UTF-8') # .... (....)
			#log(b''.join([fin, rsv1, rsv2, rsv3, opcode]).decode('UTF-8'), level=5, origin='spiderWeb', function='ws_send')
			packet += pack('B', int(b''.join([fin, rsv1, rsv2, rsv3, opcode]), 2))

			mask = b'0'
			if mask == b'1':
				mask_key = b'\x00\x00\x00\x00' # We can also use b'' and mask 0. But it'll work the same.
				for index, c in enumerate(segment):
					pass # Do something with the data.
			else:
				mask_key = b''
			payload_len = len(segment)
			extended_len = 0

			if payload_len > 65535: # If the len() is larger than a 2 byte INT
				extended_len = pack('!Q', payload_len)
				payload_len = pack('B', int(b''.join([mask, bytes('{0:0>7b}'.format(127), 'UTF-8')]),2))

			elif payload_len >= 126: # 2 bytes INT
				extended_len = pack('!H', payload_len)
				log(b'[Mask]:'.join([mask, bytes('{0:0>7b}'.format(126), 'UTF-8')]), level=5, origin='spiderWeb', function='ws_send')
				payload_len = pack('B', int(b''.join([mask, bytes('{0:0>7b}'.format(126), 'UTF-8')]),2))
			else:
				extended_len = b''
				#log(b''.join([mask, bytes('{0:0>7b}'.format(payload_len), 'UTF-8')]).decode('UTF-8'), end=' ', level=5, origin='spiderWeb', function='ws_send')
				payload_len = pack('B', int(b''.join([mask, bytes('{0:0>7b}'.format(payload_len), 'UTF-8')]),2))

			# Payload len is padded with mask
			packet += payload_len + extended_len + mask_key + segment
			log('[Flags::Data]:', {'fin': fin, 'rsv1': rsv1, 'rsv2': rsv2, 'rsv3': rsv3, 'mask': True if mask == b'1' else False, 'opcode':opcode, 'len' : len(segment), 'mask_key' : mask_key}, segment, level=10, origin='spiderWeb', function='ws_send')

			#log(data.decode('UTF-8'), origin='spiderWeb', function='ws_send')
			log('[Final::Data]:', packet, level=10, origin='spiderWeb', function='ws_send')
			self.sock.send(packet)

	def parse(self):
		if b'\r\n\r\n' in self.data and self.state == 'HTTP':
			self.headers, self.payload = self.http_parse(self.data)
			#log(self.headers, level=5, origin='spiderWeb', function='ws_send')
			#log(self.payload, level=5, origin='spiderWeb', function='ws_send')

			if b'Sec-WebSocket-Key' in self.headers and \
			  b'Upgrade' in self.headers and b'Connection' in self.headers and \
			  self.headers[b'Upgrade'].lower() == b'websocket' and \
			  b'upgrade' in self.headers[b'Connection'].lower():
				self.init_headers = self.headers.copy()
				magic_key = self.headers[b'Sec-WebSocket-Key'] + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
				hash = sha1(magic_key).digest()

				resp = b''
				resp += b'HTTP/1.1 101 Switching protocols\r\n'
				resp += b'Upgrade: websocket\r\n'
				resp += b'Connection: Upgrade\r\n'
				resp += b'Sec-WebSocket-Accept: ' + b64encode(hash) + b'\r\n'
				resp += b'\r\n'

				#log('[Connection upgraded]', level=5, origin='spiderWeb', function='ws_send')
				self.data = b''
				#self.ws_index = 0
				self.state = 'WEBSOCK'

				self.sock.send(resp)
			else:
				resp = b'HTTP/1.1 404 Not Found\r\n\r\n'
				#log'>>> 404:', self.headers, self.payload)
				self.sock.send(resp)
				self.sock.close()
				self.closed = True
				return

		elif self.state == 'WEBSOCK':
			for data in self.websock_parse():
				if data is None: continue

				log('>>', data, level=5, origin='spiderWeb', function='ws_send')
				self.ws_send(data)
		else:
			log('!!', 'Missing data/headers:', self.data, origin='spiderWeb', function='ws_send')

	def recv(self, buf=8192):
		try:
			self.data += self.sock.recv(buf)
		except:
			print('Critical error! Fix! :P')
			exit(1)

		if len(self.data) == 0:
			log('[Socket disconnected]', level=5, origin='spiderWeb', function='ws_send')
			self.sock.close()
			self.closed = True
			self.data = b''
			return

		return len(self.data)
		#self.parse()

	def close(self):
		self.sock.close()
		self.closed = True
		self.keep_alive = False

class server():
	#x = ws_client(None, None, b'\x81\xfe\x00\xd2\xa9\xbc\xc6\n\xd2\x9e\xb5o\xd8\xc9\xa3d\xca\xd9\x99d\xdb\x9e\xfc(\x9f\xd9\xa5>\x9a\xd8\xa7>\x98\x85\xa5n\xcc\xda\xf1<\xcc\xda\xfe2\x9d\x8d\xa4o\xca\x8f\xf1?\x99\x88\xf2i\xcb\x84\xf3=\x9a\x8e\xf79\x9a\x8c\xf0h\x9e\x85\xf0;\xcc\x84\xa4k\x90\xdd\xf6n\x99\x8c\xa79\xcc\x85\xf0i\x8b\x90\xe4e\xd9\xd9\xb4k\xdd\xd5\xa9d\x8b\x86\xe4{\xdc\xd9\xb4s\x8b\x90\xe4e\xcb\xd6\xa3i\xdd\x9e\xfc(\x84\x91\xa7f\xc5\xcc\xaak\xd0\xd9\xb4y\x84\x91\xe4&\x8b\xdd\xa5i\xcc\xcf\xb5U\xdd\xd3\xado\xc7\x9e\xfc(\xc8\x8b\xf6<\xca\xdf\xa52\x99\x8c\xf6k\xcf\x8c\xfe9\xca\x8d\xa29\xcf\x85\xf48\xcf\xd9\xa2i\x9b\x89\xa0n\x9e\x8f\xf2l\x9e\x8b\xa3?\x9b\x85\xf62\x9f\xd9\xf6l\xcf\x8c\xff=\x91\x88\xa7l\x9a\x8d\xf6l\x9c\x8d\xa2h\x8b\xc1\x81\xfe\x01\'\x90\n\x96i\xeb(\xe5\x0c\xe1\x7f\xf3\x07\xf3o\xc9\x07\xe2(\xacK\xa6o\xf5]\xa3n\xf7]\xa13\xf5\r\xf5l\xa1_\xf5l\xaeQ\xa4;\xf4\x0c\xf39\xa1\\\xa0>\xa2\n\xf22\xa3^\xa38\xa7Z\xa3:\xa0\x0b\xa73\xa0X\xf52\xf4\x08\xa9k\xa6\r\xa0:\xf7Z\xf53\xa0\n\xb2&\xb4\x06\xe0o\xe4\x08\xe4c\xf9\x07\xb20\xb4\x18\xe5o\xe4\x10\xb2&\xb4\x06\xf2`\xf3\n\xe4(\xacK\xf3b\xf7\x1d\xb2&\xb4\x08\xe3y\xf3\x1d\xb20\xb4\x1b\xffe\xfb6\xfcc\xe5\x1d\xb2&\xb4\x06\xe7d\xf3\x1b\xb20\xb4\n\xa1k\xf3Z\xa72\xf0\x08\xf39\xa0X\xa0k\xf0X\xf6o\xa7Q\xf4;\xa6Z\xa82\xaf[\xf32\xa1]\xf5?\xa6]\xa7i\xf7\x0f\xa9k\xa3Z\xa3:\xae[\xf6i\xa3]\xa2h\xa4\x0c\xa28\xf7^\xa08\xa5K\xbc(\xf7\n\xf3o\xe5\x1a\xcf~\xf9\x02\xf5d\xb4S\xb2k\xa1Y\xa6i\xf5\n\xa8:\xa6Y\xf1l\xa6Q\xa3i\xa7\r\xa3l\xaf[\xa2l\xf3\r\xf38\xa3\x0f\xf4=\xa5]\xf6=\xa1\x0c\xa58\xafY\xa8<\xf3Y\xf6l\xa6P\xa72\xa2\x08\xf69\xa7Y\xf6?\xa7\r\xf2(\xeb\x81\xfe\x01*7\x11Z\xeeL3)\x8bFd?\x80Tt\x05\x80E3`\xcc\x01t9\xda\x04u;\xda\x06(9\x8aRwm\xd8Rwb\xd6\x03 8\x8bT"m\xdb\x07%n\x8dU)o\xd9\x04#k\xdd\x04!l\x8c\x00(l\xdfR)8\x8f\x0epj\x8a\x07!;\xddR(l\x8d\x15=x\x81Gt(\x8fCx5\x80\x15+x\x9fBt(\x97\x15=x\x81U{?\x8dC3`\xccCt;\x83Gc5\x88^}?\x9d\x15=x\x8fDb?\x9a\x15+x\x9eBs=\xcc\x1b3;\x8dTt)\x9dhe5\x85R\x7fx\xd4\x15pm\xde\x01r9\x8d\x0f!j\xdeVwj\xd6\x04rk\x8a\x04wc\xdc\x05w?\x8aT#o\x88S&i\xdaQ&m\x8b\x02#c\xde\x0f\'?\xdeQwj\xd7\x00)n\x8fQ"k\xdeQ$k\x8aU3v\xccXf4\x8bE3`\xccT ;\x8b\x04&b\x88Vri\xd8\x06!;\x88\x06w?\xdf\x0fuk\xde\x04)b\xd7\x05rb\xd9\x03to\xde\x03&9\x8fQ(;\xdb\x04"j\xd6\x05w9\xdb\x03#8\xdcR#h\x8f\x00!h\xdd\x15l')
	#x.parse()
	#exit(1)
	def __init__(self, parsers, address='127.0.0.1', port=1337):
		self.s = socket()
		self.s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

		self.s.bind((address, port))
		self.s.listen(4)

		lookup = {self.s.fileno():'#Server'}
		poller = epoll()
		poller.register(self.s.fileno(), EPOLLIN)
		self.parsers = parsers

		if not 'sockets' in __builtins__ or ('__dict__' in __builtins__ and not 'sockets' in __builtins__.__dict__):
			try:
				__builtins__.__dict__['sockets'] = {}
				__builtins__.__dict__['io'] = {}
			except:
				__builtins__['sockets'] = {}
				__builtins__['io'] = {}

		while 1:
			for fileno, eventID in poller.poll(0.001):
				#log('\nSock event:', translation_table[eventID] if eventID in translation_table else eventID, lookup[fileno] if fileno in lookup else fileno, level=5, origin='spiderWeb', function='ws_send')
				if fileno == self.s.fileno():
					ns, na = self.s.accept()
					poller.register(ns.fileno(), EPOLLIN)
					sockets[ns.fileno()] = {'socket' : ws_client(ns, na, parsers=self.parsers), 'user' : None, 'domain' : None}
					lookup[ns.fileno()] = na

				elif fileno in sockets:
					if sockets[fileno]['socket'].closed:
						log('#Closing fileno:', fileno, level=5, origin='spiderWeb', function='ws_send')
						poller.unregister(fileno)
						del sockets[fileno]
						del lookup[fileno]
					else:
						sockets[fileno]['socket'].recv()
						sockets[fileno]['socket'].parse()
				else:
					log('Fileno not in sockets?', level=5, origin='spiderWeb', function='ws_send')