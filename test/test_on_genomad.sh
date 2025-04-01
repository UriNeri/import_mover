
micromamba activate genomad 

alias genomad_mover='python /clusterfs/jgi/scratch/science/metagen/neri/code/blits/blipit/import_mover.py  --whitelist "pathlib,multiprocessing,re,shutil,CONTEXT_SETTINGS,io,List,typing" --ignore-files ".*_test\.py$"' #|__init__\.py$"

cd test
git clone https://github.com/apcamargo/genomad/
cd genomad/genomad

echo " #### vanilla - cold run ####" > times.bc
hyperfine --warmup 0 --max-runs 1 'python cli.py'  >> times.bc
echo " #### vanilla - warm run ####" >> times.bc
hyperfine --warmup 3 --max-runs 3 'python cli.py'  >> times.bc
cat times.bc
# moving some imports to relevant functions
for file in *.py; do
    echo "$file"
    if [ -f "$file" ]; then
        genomad_mover "$file" -o "$file" --keep-old-imports --remove-unused-imports
    fi
done

echo "#### mover - cold run ####" >> times.bc
hyperfine --warmup 0 --max-runs 1 'python cli.py' >> times.bc

echo "#### mover - warm run ####" >> times.bc
hyperfine --warmup 3 --max-runs 3 'python cli.py'  >> times.bc

cat times.bc



#vanila 
python ./cli.py  4.22s user 0.23s system 135% cpu 3.293 total

# some imports moved to relevant functions
python ./cli.py  0.14s user 0.03s system 28% cpu 0.577 total