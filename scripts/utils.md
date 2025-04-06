# Helpfull commands

Create VMs
```bash
uv run pxm-create -n 10
```

Start VMs
```bash
uv run pxm-start
```

Update package
```bash
bash scripts/run_commands.sh "source flexfl/venv/bin/activate && pip install --upgrade flexfl"
```

Clear results
```bash
bash scripts/run_commands.sh "rm -rf flexfl/results"
```

Gather results
```bash
bash scripts/gather_results.sh # also clears results
```

Kill VMs processes
```bash
bash scripts/run_commands.sh "pkill screen"
```

Sync Workers clocks
```bash
bash scripts/run_commands.sh -w "sudo chronyc makestep"
```

Check Workers clocks
```bash
bash scripts/run_commands.sh -v -w "chronyc tracking"
```