

# loop 10 times
for i in {1..10}
do
    # print the current iteration
    echo "Iteration $i" && 
    sleep 3 && 
    echo "Iteration $i done" &
done
# wait for all background jobs to finish
wait
# print a message when all jobs are done
echo "All iterations completed!"