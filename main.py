import subprocess
import csv
import argparse
import sys

# ANSI escape sequences for colored output
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


def start_engine(engine_path):
    return subprocess.Popen(
        engine_path,
        universal_newlines=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        bufsize=1
    )


def send_command(engine, command):
    engine.stdin.write(command + '\n')


def read_response(engine):
    lines = []
    while True:
        line = engine.stdout.readline().strip()
        if line.startswith('bestmove'):
            lines.append(line)
            break
        lines.append(line)
    return lines


def get_best_move(engine, fen, depth):
    send_command(engine, "ucinewgame")
    send_command(engine, f'position fen {fen}')
    send_command(engine, f'go depth {depth}')
    response = read_response(engine)
    for line in response:
        if line.startswith('bestmove'):
            return line.split()[1]
    return None


def test_positions(csv_file, engine_path, depth=20, hash=64):
    correct_count = 0
    total_count = 0

    engine = start_engine(engine_path)

    send_command(engine, "uci")
    send_command(engine, f"setoption name Hash value {hash}")

    # Read and process the test position file
    with open(csv_file, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            total_count += 1
            fen = row['position']
            expected_bestmove = row['bestmove']

            print(f"FEN: {fen}")
            print(f"Expected best move: {expected_bestmove}", end='')
            sys.stdout.flush()

            engine_bestmove = get_best_move(engine, fen, depth)

            if engine_bestmove == expected_bestmove:
                correct_count += 1
                correctness_msg = f"{GREEN}CORRECT{RESET}"
            else:
                correctness_msg = f"{RED}INCORRECT{RESET}, Engine found: {engine_bestmove}"

            print(f", {correctness_msg}")

    # Send the quit command to the engine and wait for it to terminate
    send_command(engine, 'quit')
    engine.wait()

    success_percentage = (correct_count / total_count) * 100 if total_count > 0 else 0

    # Summary
    print("\nSummary of Results:")
    print(f"Total positions: {total_count}")
    print(f"Correctly identified best moves: {correct_count}")
    print(f"Success rate: {success_percentage:.2f}%")


def main():
    parser = argparse.ArgumentParser(description="Test a chess engine against a set of king safety positions.")
    parser.add_argument('engine_path', help='The path to the UCI-compatible chess engine executable.')
    parser.add_argument('depth', type=int, help='The search depth for the chess engine.')
    parser.add_argument('--hash', default=64, type=int, help='The hash size for the chess engine.')
    parser.add_argument('--csv_file', default='positions.csv',
                        help='The path to the CSV file containing FEN positions and best moves.')

    args = parser.parse_args()

    test_positions(args.csv_file, args.engine_path, args.depth, args.hash)


if __name__ == '__main__':
    main()
