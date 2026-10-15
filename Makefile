GROUP ?= 239.69.11.44
PORT ?= 5004


controller-local:
	python3 -m controller.main --group $(GROUP) --port $(PORT)

receiver-local:
	python3 -m receiver.main