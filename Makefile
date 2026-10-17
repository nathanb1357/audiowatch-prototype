GROUP ?= 239.69.11.44
PORT ?= 5004
SECONDS ?= 5


controller-local:
	python3 -m controller.main --group $(GROUP) --port $(PORT)

receiver-local:
	python3 -m receiver.main

latency-report:
	python3 -m tests.report_loss_latency --seconds $(SECONDS)