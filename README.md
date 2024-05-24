# Engine Position Tester

## Usage

### Using the Default CSV File

#### Using go nodes command
```sh
python main.py --engine /path/to/your_engine --nodes 10_000_000 --threads 4
```

#### Using go depth command
```sh
python main.py --engine /path/to/your_engine --depth 20 --threads 4
```

### Using Custom CSV File
```sh
python main.py --engine /path/to/your_engine --depth 20 --threads 4 --csv_file your_test_file.csv
```
