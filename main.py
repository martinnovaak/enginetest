import subprocess
import csv
import argparse
import sys
from ast import literal_eval
from concurrent.futures import ThreadPoolExecutor, as_completed

# ANSI escape sequences for colored output
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"

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
        print(f"{RED}Error: Engine not found at {engine_path}{RESET}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"{RED}Error starting engine {engine_path}: {e}{RESET}", file=sys.stderr)
        sys.exit(1)

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
    if len(bestmoves) == 1:
        return bestmoves[0]
    return " or ".join(bestmoves)

def evaluate_single_engine_position(engine_path, fen, expected_bestmoves, search_command, hash_size):
    """Evaluates a single FEN position for one engine."""
    engine = start_engine(engine_path)
    send_command(engine, "uci") # Ensure UCI is set for options like Hash

    engine_bestmove = get_best_move_from_engine(engine, fen, search_command, hash_size)

    send_command(engine, 'quit')
    engine.wait()

    is_correct = engine_bestmove in expected_bestmoves if engine_bestmove else False
    return fen, expected_bestmoves, engine_bestmove, is_correct

def test_single_engine_positions(csv_file, engine_path, search_command, hash_size=64, num_threads=1, num_positions=None):
    """Tests a single chess engine against a set of positions."""
    correct_count = 0
    total_count = 0

    with open(csv_file, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        positions_data = [
            (i + 1, row['position'], literal_eval(row['bestmove']))
            for i, row in enumerate(reader)
            if num_positions is None or i < num_positions
        ]

    total_positions = len(positions_data)
    incorrect_positions = []
    engine_name = engine_path.split('/')[-1]

    print(f"Starting single engine test for {CYAN}{engine_name}{RESET} on {total_positions} positions...")

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = {
            executor.submit(evaluate_single_engine_position, engine_path, fen, expected_bestmoves, search_command, hash_size): (index, fen, expected_bestmoves)
            for index, fen, expected_bestmoves in positions_data
        }

        for future in as_completed(futures):
            index, fen, expected_bestmoves = futures[future]
            total_count += 1
            try:
                fen, expected_bestmoves, engine_bestmove, is_correct = future.result()
            except Exception as exc:
                print(f"{RED}Position {index}: Generated an exception: {exc}{RESET}")
                print(f"FEN: {fen}, Expected: {format_bestmoves(expected_bestmoves)}")
                continue

            formatted_bestmoves = format_bestmoves(expected_bestmoves)
            print(f"\n{YELLOW}{index}/{total_positions} FEN: {fen}{RESET}")
            print(f"Expected best moves: {formatted_bestmoves}")

            correctness_msg = f"{GREEN}CORRECT{RESET}" if is_correct else f"{RED}INCORRECT{RESET}"
            print(f"Engine ({BLUE}{engine_name}{RESET}): {engine_bestmove}, Result: {correctness_msg}")

            if is_correct:
                correct_count += 1
            else:
                incorrect_positions.append({'position': fen, 'engine_move': engine_bestmove})

    # Write incorrect positions to CSV file
    with open(f"incorrect_{engine_name}.csv", mode='w', newline='', encoding='utf-8') as outfile:
        fieldnames = ['position', 'engine_move']
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(incorrect_positions)
    print(f"\n{RED}Incorrect positions for {engine_name} saved to incorrect_{engine_name}.csv{RESET}")

    success_percentage = (correct_count / total_count) * 100 if total_count > 0 else 0

    # Summary
    print(f"\n{YELLOW}--- Summary of Results for {engine_name} ---{RESET}")
    print(f"Test suite: {csv_file}")
    print(f"Total positions tested: {total_count}")
    print(f"Correctly identified best moves: {correct_count}")
    print(f"Success rate: {success_percentage:.2f}%")


def evaluate_two_engines_position(engine1_path, engine2_path, fen, expected_bestmoves, search_command1, search_command2, hash_size):
    """Evaluates a single FEN position for two engines."""
    engine1 = start_engine(engine1_path)
    engine2 = start_engine(engine2_path)

    # Initialize UCI for both engines
    send_command(engine1, "uci")
    send_command(engine2, "uci")

    engine1_bestmove = get_best_move_from_engine(engine1, fen, search_command1, hash_size)
    engine2_bestmove = get_best_move_from_engine(engine2, fen, search_command2, hash_size)

    send_command(engine1, 'quit')
    engine1.wait()
    send_command(engine2, 'quit')
    engine2.wait()

    engine1_is_correct = engine1_bestmove in expected_bestmoves if engine1_bestmove else False
    engine2_is_correct = engine2_bestmove in expected_bestmoves if engine2_bestmove else False

    return fen, expected_bestmoves, engine1_bestmove, engine1_is_correct, engine2_bestmove, engine2_is_correct

def test_two_engines_positions(csv_file, engine1_path, engine2_path, search_command1, search_command2, hash_size=64, num_threads=1, num_positions=None):
    """Tests two chess engines against a set of positions."""
    engine1_correct_count = 0
    engine2_correct_count = 0
    total_count = 0

    with open(csv_file, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        positions_data = [
            (i + 1, row['position'], literal_eval(row['bestmove']))
            for i, row in enumerate(reader)
            if num_positions is None or i < num_positions
        ]

    total_positions = len(positions_data)
    engine1_incorrect_positions = []
    engine2_incorrect_positions = []
    engine1_name = engine1_path.split('/')[-1]
    engine2_name = engine2_path.split('/')[-1]


    print(f"Starting engine comparison test for {CYAN}{engine1_name}{RESET} vs {CYAN}{engine2_name}{RESET} on {total_positions} positions...")

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = {
            executor.submit(evaluate_two_engines_position, engine1_path, engine2_path, fen, expected_bestmoves, search_command1, search_command2, hash_size): (index, fen, expected_bestmoves)
            for index, fen, expected_bestmoves in positions_data
        }

        for future in as_completed(futures):
            index, fen, expected_bestmoves = futures[future]
            total_count += 1
            try:
                fen, expected_bestmoves, engine1_bestmove, engine1_is_correct, engine2_bestmove, engine2_is_correct = future.result()
            except Exception as exc:
                print(f"{RED}Position {index}: Generated an exception: {exc}{RESET}")
                print(f"FEN: {fen}, Expected: {format_bestmoves(expected_bestmoves)}")
                continue

            formatted_bestmoves = format_bestmoves(expected_bestmoves)

            print(f"\n{YELLOW}{index}/{total_positions} FEN: {fen}{RESET}")
            print(f"Expected best moves: {formatted_bestmoves}")

            engine1_correctness_msg = f"{GREEN}CORRECT{RESET}" if engine1_is_correct else f"{RED}INCORRECT{RESET}"
            engine2_correctness_msg = f"{GREEN}CORRECT{RESET}" if engine2_is_correct else f"{RED}INCORRECT{RESET}"

            print(f"Engine 1 ({BLUE}{engine1_name}{RESET}): {engine1_bestmove}, Result: {engine1_correctness_msg}")
            print(f"Engine 2 ({BLUE}{engine2_name}{RESET}): {engine2_bestmove}, Result: {engine2_correctness_msg}")

            if engine1_is_correct:
                engine1_correct_count += 1
            else:
                engine1_incorrect_positions.append({'position': fen, 'engine_move': engine1_bestmove})

            if engine2_is_correct:
                engine2_correct_count += 1
            else:
                engine2_incorrect_positions.append({'position': fen, 'engine_move': engine2_bestmove})

    # Write incorrect positions to CSV files
    with open(f"incorrect_{engine1_name}.csv", mode='w', newline='', encoding='utf-8') as outfile:
        fieldnames = ['position', 'engine_move']
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(engine1_incorrect_positions)
    print(f"\n{RED}Incorrect positions for Engine 1 ({engine1_name}) saved to incorrect_{engine1_name}.csv{RESET}")

    with open(f"incorrect_{engine2_name}.csv", mode='w', newline='', encoding='utf-8') as outfile:
        fieldnames = ['position', 'engine_move']
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(engine2_incorrect_positions)
    print(f"{RED}Incorrect positions for Engine 2 ({engine2_name}) saved to incorrect_{engine2_name}.csv{RESET}")

    engine1_success_percentage = (engine1_correct_count / total_count) * 100 if total_count > 0 else 0
    engine2_success_percentage = (engine2_correct_count / total_count) * 100 if total_count > 0 else 0

    # Summary
    print(f"\n{YELLOW}--- Summary of Results ---{RESET}")
    print(f"Test suite: {csv_file}")
    print(f"Total positions tested: {total_count}")

    print(f"\n{BLUE}Engine 1 ({engine1_name}):{RESET}")
    print(f"  Correctly identified best moves: {engine1_correct_count}")
    print(f"  Success rate: {engine1_success_percentage:.2f}%")

    print(f"\n{BLUE}Engine 2 ({engine2_name}):{RESET}")
    print(f"  Correctly identified best moves: {engine2_correct_count}")
    print(f"  Success rate: {engine2_success_percentage:.2f}%")

def main():
    parser = argparse.ArgumentParser(description="Test one or two chess engines against a set of positions.")
    parser.add_argument('--engine1', required=True, help='The path to the first UCI-compatible chess engine executable.')
    parser.add_argument('--engine2', help='The path to the second UCI-compatible chess engine executable for comparison (optional).')
    parser.add_argument('--depth', type=int, help='The search depth for engine(s).')
    parser.add_argument('--nodes', type=int, help='The number of nodes for engine(s) to search.')
    parser.add_argument('--depth2', type=int, help='The search depth for the second chess engine (overrides --depth for engine2).')
    parser.add_argument('--nodes2', type=int, help='The number of nodes for the second chess engine to search (overrides --nodes for engine2).')
    parser.add_argument('--hash', default=64, type=int, help='The hash size for the chess engine(s).')
    parser.add_argument('--csv_file', default='king_safety.csv',
                        help='The path to the CSV file containing FEN positions and best moves.')
    parser.add_argument('--concurrency', default=1, type=int, help='The number of threads to use. For two engines, each thread runs two engine instances.')
    parser.add_argument('--num_positions', type=int, help='The number of positions to load from the CSV file (for testing a subset).')

    args = parser.parse_args()

    # Determine search command for Engine 1
    if args.depth and args.nodes:
        print(f"{RED}Error: Please specify either --depth or --nodes for Engine 1, not both.{RESET}", file=sys.stderr)
        sys.exit(1)
    if args.depth:
        search_command1 = f'go depth {args.depth}'
    elif args.nodes:
        search_command1 = f'go nodes {args.nodes}'
    else:
        print(f"{RED}Error: Please specify either --depth or --nodes.{RESET}", file=sys.stderr)
        sys.exit(1)

    if args.engine2:
        # Two-engine comparison
        if args.depth2 and args.nodes2:
            print(f"{RED}Error: Please specify either --depth2 or --nodes2 for Engine 2, not both.{RESET}", file=sys.stderr)
            sys.exit(1)

        search_command2 = search_command1 # Default to Engine 1's command

        if args.depth2:
            search_command2 = f'go depth {args.depth2}'
        elif args.nodes2:
            search_command2 = f'go nodes {args.nodes2}'

        test_two_engines_positions(args.csv_file, args.engine1, args.engine2, search_command1, search_command2, args.hash, args.concurrency, args.num_positions)
    else:
        # Single-engine test
        test_single_engine_positions(args.csv_file, args.engine1, search_command1, args.hash, args.concurrency, args.num_positions)

if __name__ == '__main__':
    main()
