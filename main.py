import subprocess
import csv
import argparse
import sys
from ast import literal_eval
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

# ANSI escape sequences for colored output
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
YELLOW = "\033[93m"
BLUE = "\033[94m"


def start_engine(engine_path):
    """Starts a UCI chess engine process."""
    try:
        return subprocess.Popen(
            engine_path,
            universal_newlines=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # Redirect stderr to avoid printing it
            bufsize=1
        )
    except FileNotFoundError:
        print(f"{RED}Error: Engine not found at {engine_path}{RESET}")
        raise FileNotFoundError(f"Engine not found: {engine_path}")
    except Exception as e:
        print(f"{RED}Error starting engine {engine_path}: {e}{RESET}")
        raise Exception(f"Error starting engine {engine_path}: {e}")


def send_command(engine, command):
    """Sends a command to the engine's stdin."""
    engine.stdin.write(command + '\n')
    engine.stdin.flush()


def read_response(engine):
    """Reads lines from the engine's stdout until 'bestmove' is encountered."""
    lines = []
    while True:
        line = engine.stdout.readline().strip()
        lines.append(line)
        if line.startswith('bestmove'):
            break
    return lines


def get_engine_name(engine_path):
    """Starts an engine, gets its UCI 'id name', and quits it."""
    try:
        engine_process = start_engine(engine_path)
        send_command(engine_process, "uci")
        name = os.path.basename(engine_path) # Default to executable name if UCI name isn't found

        while True:
            line = engine_process.stdout.readline().strip()
            if line.startswith("id name"):
                name = line.split("id name", 1)[1].strip()
            elif line == "uciok":
                break

        send_command(engine_process, "quit")
        engine_process.wait(timeout=5)
        return name
    except Exception as e:
        print(f"{RED}Warning: Could not get UCI name for {engine_path}. Using executable name. Error: {e}{RESET}")
        return os.path.basename(engine_path) # Fallback to executable name


def get_best_move_from_engine(engine, fen, search_command, hash_size):
    """Gets the best move from a single engine for a given FEN."""
    send_command(engine, "ucinewgame")
    send_command(engine, "isready")
    while True: # Wait for 'readyok'
        line = engine.stdout.readline().strip()
        if line == 'readyok':
            break

    send_command(engine, f"setoption name Hash value {hash_size}")
    send_command(engine, f'position fen {fen}')
    send_command(engine, search_command)
    response = read_response(engine)
    for line in response:
        if line.startswith('bestmove'):
            parts = line.split()
            if len(parts) >= 2:
                return parts[1]
    return None


def format_bestmoves(bestmoves):
    """Formats a list of best moves for display."""
    if not bestmoves:
        return "N/A"
    if isinstance(bestmoves, list):
        return " or ".join(bestmoves)
    return str(bestmoves)


def evaluate_multiple_engines_position(engine_configs, fen, expected_bestmoves, search_command, hash_size):
    """Evaluates a single FEN position for multiple engines.
       engine_configs is a list of (engine_path, uci_name) tuples.
    """
    results_for_position = []
    engine_processes = {}  # Store engine process objects to ensure they are quit

    for engine_path, uci_name in engine_configs:
        engine_bestmove = None
        is_correct = False
        try:
            engine_process = start_engine(engine_path)
            engine_processes[engine_path] = engine_process  # Store the process
            send_command(engine_process, "uci")

            engine_bestmove = get_best_move_from_engine(engine_process, fen, search_command, hash_size)
            is_correct = engine_bestmove in expected_bestmoves if engine_bestmove else False

        except (FileNotFoundError, Exception) as e:
            print(f"{RED}Error evaluating {uci_name} ({engine_path}) for FEN {fen}: {e}{RESET}")
            # Mark as incorrect if engine failed to run/return move
            is_correct = False
        finally:
            if engine_path in engine_processes and engine_processes[engine_path].poll() is None:  # If process is still running
                try:
                    send_command(engine_processes[engine_path], 'quit')
                    engine_processes[engine_path].wait(timeout=5)  # Wait with a timeout
                except subprocess.TimeoutExpired:
                    engine_processes[engine_path].kill()  # Force kill if it doesn't quit
                    print(f"{YELLOW}Warning: {uci_name} ({engine_path}) did not quit gracefully and was killed.{RESET}")
            elif engine_path in engine_processes and engine_processes[engine_path].poll() is not None:
                # Process already terminated
                pass

        results_for_position.append({
            'engine_path': engine_path,
            'engine_name': uci_name,
            'bestmove': engine_bestmove,
            'is_correct': is_correct
        })
    return fen, expected_bestmoves, results_for_position


def test_engines_against_positions(csv_file, engine_configs, search_command, hash_size=64, num_threads=1, num_positions=None):
    """Tests multiple chess engines against a set of positions.
       engine_configs is a list of (engine_path, uci_name) tuples.
    """

    # Initialize data structures for overall results
    engine_correct_counts = {path: 0 for path, _ in engine_configs}
    engine_incorrect_positions = {path: [] for path, _ in engine_configs}
    total_count = 0

    with open(csv_file, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        positions_data = [
            (i + 1, row['position'], literal_eval(row['bestmove']))
            for i, row in enumerate(reader)
            if num_positions is None or i < num_positions
        ]

    total_positions = len(positions_data)

    engine_uci_names = [name for _, name in engine_configs]
    print(f"Starting test for {len(engine_configs)} engines: {BLUE}{', '.join(engine_uci_names)}{RESET} on {total_positions} positions...")

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = {
            executor.submit(evaluate_multiple_engines_position, engine_configs, fen, expected_bestmoves, search_command, hash_size): (index, fen, expected_bestmoves)
            for index, fen, expected_bestmoves in positions_data
        }

        for future in as_completed(futures):
            index, fen, expected_bestmoves = futures[future]
            total_count += 1
            try:
                fen, expected_bestmoves, results_for_position = future.result()
            except Exception as exc:
                print(f"{RED}Position {index}: Generated an exception: {exc}{RESET}")
                print(f"FEN: {fen}, Expected: {format_bestmoves(expected_bestmoves)}")
                continue

            formatted_bestmoves = format_bestmoves(expected_bestmoves)
            print(f"\n{YELLOW}{index}/{total_positions} FEN: {fen}{RESET}")
            print(f"Expected best moves: {formatted_bestmoves}")

            for engine_result in results_for_position:
                engine_path = engine_result['engine_path']
                uci_name = engine_result['engine_name']
                engine_bestmove = engine_result['bestmove']
                is_correct = engine_result['is_correct']

                correctness_msg = f"{GREEN}CORRECT{RESET}" if is_correct else f"{RED}INCORRECT{RESET}"
                print(f"Engine ({BLUE}{uci_name}{RESET}): {engine_bestmove}, Result: {correctness_msg}")

                if is_correct:
                    engine_correct_counts[engine_path] += 1
                else:
                    engine_incorrect_positions[engine_path].append({'position': fen, 'engine_move': engine_bestmove})

    # Write incorrect positions to CSV files for each engine
    print(f"\n--- Saving Incorrect Positions ---")
    for engine_path, incorrect_list in engine_incorrect_positions.items():
        uci_name = next((name for path, name in engine_configs if path == engine_path), os.path.basename(engine_path))
        output_filename = f"incorrect_{uci_name.replace(' ', '_').replace('/', '_')}.csv"
        with open(output_filename, mode='w', newline='', encoding='utf-8') as outfile:
            fieldnames = ['position', 'engine_move']
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(incorrect_list)
        print(f"Incorrect positions for {uci_name} saved to {output_filename}")

    # Summary
    print(f"\n{YELLOW}--- Summary of All Engine Results ---{RESET}")
    print(f"Test suite: {csv_file}")
    print(f"Total positions tested: {total_count}")
    print(f"Search Setting: {search_command.replace('go ', '')}{RESET}")

    for engine_path, uci_name in engine_configs:
        correct_count = engine_correct_counts[engine_path]
        success_percentage = (correct_count / total_count) * 100 if total_count > 0 else 0

        print(f"\n{BLUE}Engine: {uci_name}{RESET}")
        print(f"    Correctly identified best moves: {correct_count}")
        print(f"    Success rate: {success_percentage:.2f}%")


def main():
    parser = argparse.ArgumentParser(description="Test one or more chess engines against a set of positions.")
    parser.add_argument('--engines', nargs='+', required=True,
                        help='Paths to UCI-compatible chess engine executables (space-separated). E.g., --engines ./stockfish ./komodo')
    parser.add_argument('--depth', type=int, help='The search depth for all chess engines.')
    parser.add_argument('--nodes', type=int, help='The number of nodes for all chess engines to search.')
    parser.add_argument('--hash', default=64, type=int, help='The hash size for all chess engines.')
    parser.add_argument('--csv_file', default='king_safety.csv',
                        help='The path to the CSV file containing FEN positions and best moves.')
    parser.add_argument('--concurrency', default=1, type=int,
                        help='The number of threads to use. Each thread will run all specified engine instances for a position.')
    parser.add_argument('--num_positions', type=int,
                        help='The number of positions to load from the CSV file (for testing a subset).')

    args = parser.parse_args()

    # Determine search command for all engines
    if args.depth and args.nodes:
        print(f"{RED}Error: Please specify either --depth or --nodes, not both.{RESET}")
        sys.exit(1)
    if args.depth:
        search_command = f'go depth {args.depth}'
    elif args.nodes:
        search_command = f'go nodes {args.nodes}'
    else:
        print(f"{RED}Error: Please specify either --depth or --nodes.{RESET}")
        sys.exit(1)

    # Validate engine paths and get UCI names
    engine_configs = [] # List of (path, uci_name) tuples
    for engine_path in args.engines:
        if not os.path.exists(engine_path):
            print(f"{RED}Error: Engine executable not found at '{engine_path}'. Please check the path.{RESET}")
            sys.exit(1)
        if not os.path.isfile(engine_path):
            print(f"{RED}Error: '{engine_path}' is not a file. Please provide path to an executable file.{RESET}")
            sys.exit(1)

        uci_name = get_engine_name(engine_path)
        engine_configs.append((engine_path, uci_name))

    test_engines_against_positions(args.csv_file, engine_configs, search_command, args.hash, args.concurrency, args.num_positions)


if __name__ == '__main__':
    main()
