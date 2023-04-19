

cryo: frappy/cfg/cryo_cfg.py
	python3 frappy/bin/frappy-server frappy/cfg/cryo_cfg.py  > cryo_log.txt  2>&1 & jobs -p > pids.txt

	



test: venv cryo  ## 🎯 Unit tests for Flask app
	sleep 1

	. .venv/bin/activate && pytest -v test/test.py
	kill $$(cat pids.txt)







venv: .venv/touchfile

.venv/touchfile: requirements.txt frappy/requirements.txt
	python3 -m venv .venv
	. .venv/bin/activate; pip install -Ur requirements.txt; pip install -Ur frappy/requirements.txt
	touch .venv/touchfile



clean:  ## 🧹 Clean up project
	rm -rf .venv
	rm -rf tests/node_modules
	rm -rf tests/package*
	rm -rf test-results.xml
	rm -rf __pycache__
	rm -rf .pytest_cache
	rm -rf pids.txt
	rm -rf *_log.txt
