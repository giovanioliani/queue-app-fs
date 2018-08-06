from collections import deque
import json
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.internet.protocol import ClientFactory
from twisted.internet.protocol import Protocol
from twisted.internet import reactor


class QueueManager(object):
	def __init__(self):
		# Stack with available operators (LIFO)
		self.available = ['B', 'A']
		# Contains Ids of calls waiting to be answered (FIFO)
		self.waiting = deque()
		# Contains mappings from busy operators into their calls and vice-versa
		self.busy = dict()
		# Contains mapping from ringing calls into their operators and vice-versa
		self.ringing = dict()

	# Removes a mapping from a call to an operator and its inverse
	# Returns the value id maps to
	def dictPopElement(self, mapping, id):
		ret = mapping.pop(id)
		del mapping[ret]
		return ret

	# Adds a mapping from a call to an operator and its inverse
	def dictInsertElement(self, mapping, op_id, call_id):
		mapping[op_id] = call_id
		mapping[call_id] = op_id

	def do_call(self, call_id):
		ret = ''.join(["Call ", call_id, " received\n"])
		# If there are no operators available, enqueue the call
		if len(self.available) == 0:
			self.waiting.append(call_id)
			ret = ''.join([ret, "Call ", call_id, " waiting in queue"])
		else:
			# Get the operator from the available stack, then add the call to
			# the ringing mapping
			op_id = self.available.pop()
			self.dictInsertElement(self.ringing, op_id, call_id)
			ret = ''.join([ret, "Call ", call_id, " ringing for operator ", op_id])
		return ret

	def do_answer(self, op_id):
		call_id = self.dictPopElement(self.ringing,op_id)
		self.dictInsertElement(self.busy, op_id, call_id)
		return ''.join(["Call ", call_id, " answered by operator ", op_id])

	def do_reject(self, op_id):
		# Remove operator from ringing mapping
		call_id = self.dictPopElement(self.ringing, op_id)
		ret = ''.join(["Call ", call_id, " rejected by operator ", op_id, "\n"])
		# If there is another operator available, the call must ring for him first
		if len(self.available) != 0:
			# Get the other available operator, then enqueue the one who rejected the call
			ringed_op = op_id
			op_id = self.available.pop()
			self.available.append(ringed_op)
		# If there is no other operator available, the call will just ring the same operator
		self.dictInsertElement(self.ringing, op_id, call_id)
		return ''.join([ret, "Call ", call_id, " ringing for operator ", op_id])

	def do_hangup(self, call_id):
		# If the call had been answered by some operator
		if call_id in self.busy:
			op_id = self.dictPopElement(self.busy, call_id)
			ret = ''.join(["Call ", call_id, " finished and operator ", op_id, " available"])
			# If there are calls waiting, get one and ring the operator
			if len(self.waiting) > 0:
				call_id = self.waiting.popleft()
				self.dictInsertElement(self.ringing, op_id, call_id)
				ret = ''.join([ret, "\n", "Call ", call_id, " ringing for operator ", op_id])
			else:
				self.available.append(op_id)
		# If the call was ringing for some operator
		elif call_id in self.ringing:
			op_id = self.dictPopElement(self.ringing, call_id)
			ret = ''.join(["Call ", call_id, " missed"])
			if len(self.waiting) > 0:
				call_id = self.waiting.popleft()
				self.dictInsertElement(self.ringing, op_id, call_id)
				ret = ''.join([ret, "\n", "Call ", call_id, " ringing for operator ", op_id])
			else:
				self.available.append(op_id)
		# If the call was waiting in queue
		else:
			self.waiting.remove(call_id)
			ret = ''.join(["Call ", call_id, " missed"])
		return ret

class ManagerInterfaceProtocol(Protocol):
	def __init__(self, factory):
		self.factory = factory

	def dataReceived(self, data):
		# Decodes JSON command string received from client
		command = json.loads(data).values()
		# Gets operation result from QueueManager object
		result = getattr(self.factory.queues, "do_" + command[0])(command[1])
		# Encodes operation result and sends to the client
		self.transport.write(json.dumps({"response": result}))

class ManagerInterfaceFactory(ClientFactory):
	def __init__(self):
		self.queues = QueueManager()

	def buildProtocol(self, addr):
		return ManagerInterfaceProtocol(self)

endpoint = TCP4ServerEndpoint(reactor, 5679)
endpoint.listen(ManagerInterfaceFactory())
reactor.run()