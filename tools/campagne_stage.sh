#!/bin/zsh
# Étape d'une campagne : chaque ligne de l'argument = "corpus producteur prompt modèle [max_side]".
set -u
export PYTHONPATH=$HOME/saknussemm/src:$HOME/saknussemm-demo/backend
export MISTRAL_KEY_FILE=$HOME/corpus-vt/resultats/.mk
PY=$HOME/saknussemm/.venv/bin/python
while read -r line; do
  [ -z "$line" ] && continue
  echo "### $(date +%H:%M:%S) $line"
  $PY $HOME/hans/tools/campagne.py ${=line} || echo "### ÉCHEC DU BRAS : $line"
done <<< "$1"
echo "### CAMPAGNE TERMINÉE $(date +%H:%M:%S)"
