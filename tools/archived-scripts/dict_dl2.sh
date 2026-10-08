#!/bin/bash
cd "C:/Users/zzl/Desktop/hx"
URL="https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/Extras/CID-Synonym-filtered.gz"
T=976534762
N=4
STEP=$(( (T + N - 1) / N ))
for i in $(seq 0 $((N-1))); do
  a=$(( i * STEP ))
  b=$(( a + STEP - 1 ))
  if [ "$b" -ge "$T" ]; then b=$(( T - 1 )); fi
  want=$(( b - a + 1 ))
  part="tools/tmp/dict_part_$i.bin"
  got=$(stat -c%s "$part" 2>/dev/null || echo 0)
  for try in 1 2 3 4 5 6; do
    if [ "$got" -eq "$want" ]; then break; fi
    curl -s --ssl-no-revoke -x http://127.0.0.1:7890 --max-time 1200 --retry 3 --retry-delay 3 \
         -r "$a-$b" -o "$part" "$URL"
    got=$(stat -c%s "$part" 2>/dev/null || echo 0)
    echo "chunk $i range $a-$b want=$want got=$got try=$try"
  done
done
echo "ALLCHUNKS_DONE"
cat tools/tmp/dict_part_0.bin tools/tmp/dict_part_1.bin tools/tmp/dict_part_2.bin tools/tmp/dict_part_3.bin > tools/tmp/dict_synonyms.new
echo "concat size=$(stat -c%s tools/tmp/dict_synonyms.new)"
