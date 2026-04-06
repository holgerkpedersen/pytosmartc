# Python-to-Signum SmartC Compiler

Compile Python-like smart contracts to Signum SmartC code that deploys to the Signum blockchain.

## What It Does

This compiler translates Python-like DSL contracts into SmartC C code, which then compiles to Signum AT (Automated Transactions) assembly. Use it to write smart contracts in a readable Python syntax and deploy them to the Signum testnet or mainnet.

## Installation

```bash
pip install -e .
```

Or from source:
```bash
git clone https://github.com/yourusername/pytosmartc.git
cd pytosmartc
pip install -e .
```

## Usage

Compile a Python contract to SmartC:
```bash
pytosmartc vault.py -o vault.smart.c
```

Deploy to Signum blockchain:
1. Copy the generated `.smart.c` file
2. Go to [SmartC Web IDE](https://deleterium.info/SmartC/)
3. Paste the code and click Compile
4. Copy the AT assembly output
5. Deploy using [Signum Wallet](https://wallet.signum.network/)

## Example Contracts

The project includes 5 reference implementations:

| Contract | Purpose | Functions |
|----------|---------|-----------|
| **vault.py** | Time-locked vault | `lock()`, `withdraw()`, `get_status()` |
| **mytoken.py** | ERC20-style token | `transfer()`, `mint()`, `burn()` |
| **lottery.py** | Lottery system | `start_lottery()`, `buy_ticket()`, `draw_winner()` |
| **crowdfund.py** | Crowdfunding campaign | `setup_campaign()`, `contribute()`, `withdraw_*()` |
| **multisig.py** | 3-owner multisig wallet | `setup_owners()`, `propose_transaction()`, `approve_transaction()` |

## Known Limitations

| Limitation | Workaround |
|------------|-----------|
| No JSON returns from functions | Return numeric status codes instead (see contracts for examples) |
| Function parameters must not conflict with global variable names | Compiler auto-renames conflicting parameters (e.g., `to` → `param_to`) |
| Strings > 8 bytes must be numeric codes | Use numeric constants: `"withdrawn"` → `1`, `"ready"` → `2` |
| No loops or recursion | Use if/else statements instead |
| All variables are global (persistent) | Design contracts with this in mind |

## Testing

Run the unit test suite:
```bash
pytest test_smart_contracts.py -v
```

Or:
```bash
python -m unittest test_smart_contracts.py -v
```

All tests use a `MockBlockchain` harness and do not require actual blockchain interaction.

## Architecture

- **signum_compiler.py** — Main compiler (1600 lines, zero external dependencies)
  - `PythonToIRConverter` — Parse Python AST to intermediate representation
  - `SmartCDirectGenerator` — Generate SmartC code directly from AST
  - Built-in Signum mappings: `sender()` → `getCreator()`, `block_height()` → `getCurrentBlockheight()`, etc.

- **test_smart_contracts.py** — 22 unit tests covering all contracts

## Development

To modify the compiler:
1. Edit `signum_compiler.py`
2. Test with: `pytest test_smart_contracts.py -v`
3. Compile contracts: `python signum_compiler.py *.py`
4. Verify SmartC output in [Web IDE](https://deleterium.info/SmartC/)

## Requirements

- Python 3.10+
- No external dependencies (stdlib only)

## License

MIT

## References

All links verified and functional as of 2026-04-06.

- [Signum Blockchain](https://signum.network/)
- [SmartC Documentation](https://github.com/deleterium/SmartC)
- [SmartC Web IDE](https://deleterium.info/SmartC/)
- [Signum Wallet](https://wallet.signum.network/)

**Link Status:** ✅ All 4 external links validated and accessible
