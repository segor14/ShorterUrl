import os
import subprocess
import time
import pandas as pd
import signal

def run_test(users, spawn_rate, duration, host="http://localhost:8000"):
    print(f"Running test with {users} users, spawn rate {spawn_rate}, duration {duration}...")
    csv_prefix = f"tests/load/results_u{users}"
    cmd = [
        "locust",
        "-f", "tests/load/locustfile.py",
        "--headless",
        "-u", str(users),
        "-r", str(spawn_rate),
        "-t", duration,
        "--host", host,
        "--csv", csv_prefix,
        "--only-summary"
    ]
    
    subprocess.run(cmd)
    
    stats_file = f"{csv_prefix}_stats.csv"
    if os.path.exists(stats_file):
        df = pd.read_csv(stats_file)
        agg = df[df['Name'] == 'Aggregated']
        if not agg.empty:
            rps = agg['Requests/s'].values[0]
            avg_resp_time = agg['Average Response Time'].values[0]
            fail_ratio = agg['Failure Count'].values[0] / agg['Request Count'].values[0] if agg['Request Count'].values[0] > 0 else 0
            return rps, avg_resp_time, fail_ratio
    return 0, 0, 0

def main():
    host = "http://localhost:8000"
    results = []
    
    user_counts = [10, 50, 100, 200, 500]
    duration = "30s"
    
    print("Starting load tests to find max RPS...")
    
    for users in user_counts:
        spawn_rate = max(users // 10, 1)
        rps, avg_time, fail_ratio = run_test(users, spawn_rate, duration, host)
        print(f"Users: {users}, RPS: {rps:.2f}, Avg Time: {avg_time:.2f}ms, Fail Ratio: {fail_ratio:.2%}")
        
        results.append({
            "users": users,
            "rps": rps,
            "avg_time": avg_time,
            "fail_ratio": fail_ratio
        })
        
        if fail_ratio > 0.05:
            print("Failure ratio exceeded 5%. Stopping tests.")
            break
        
        time.sleep(5)
        
    summary_df = pd.DataFrame(results)
    summary_df.to_csv("tests/load/load_test_summary.csv", index=False)
    print("\nLoad test summary saved to tests/load/load_test_summary.csv")
    
    max_rps = summary_df['rps'].max()
    print(f"\nEstimated Max RPS: {max_rps:.2f}")

if __name__ == "__main__":
    main()
