#!/bin/sh

SCRIPT_DIR=$(dirname $(realpath $0))

$SCRIPT_DIR/rename-lens.sh 'F22' 'F32'
$SCRIPT_DIR/rename-lens.sh 'F16' 'F22'
$SCRIPT_DIR/rename-lens.sh 'F11' 'F16'
$SCRIPT_DIR/rename-lens.sh 'F8' 'F11'
$SCRIPT_DIR/rename-lens.sh 'F5.6' 'F8'
$SCRIPT_DIR/rename-lens.sh 'F4' 'F5.6'
$SCRIPT_DIR/rename-lens.sh 'F2.8' 'F4'
$SCRIPT_DIR/rename-lens.sh 'F2' 'F2.8'
$SCRIPT_DIR/rename-lens.sh 'F1.8' 'F2.5'
