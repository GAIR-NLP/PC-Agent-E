#!/bin/bash

vllm serve "henryhe0123/PC-Agent-E" --tensor-parallel-size 4 --port 8030
