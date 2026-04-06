# Python-to-Signum SmartC Compiler

Compile Python-like smart contracts to Signum SmartC code that deploys to the Signum blockchain.

## What It Does

This compiler translates Python-like DSL contracts into SmartC C code, which then compiles to Signum AT (Automated Transactions) assembly. Use it to write smart contracts in a readable Python syntax and deploy them to the Signum testnet or mainnet.

## Installation

Install from the repository:
```bash
git clone https://github.com/holgerkpedersen/pytosmartc.git
cd pytosmartc
pip install -e .
```

Or with pip:
```bash
pip install -e .
```

## Usage

Compile a Python contract to SmartC:
```bash
pytosmartc vault.py -o vault.smart.c
```

Deploy to Signum blockchain:
1. Compile your Python contract: `pytosmartc mycontract.py -o mycontract.smart.c`
2. Compile SmartC to AT assembly using one of:
   - **Build SmartC locally**: Clone [deleterium/smartc-web-ui](https://smartc.signum-network.dev/), build, and use locally
   - **Use npm package**: `npm install -g smartc-signum-compiler` then `smartc mycontract.smart.c`
   - **Use SC-Simulator**: [deleterium/SC-Simulator](https://github.com/deleterium/SC-Simulator) for testing
3. Copy the generated AT assembly code
4. Deploy using [Signum Wallet](https://github.com/signum-network/signum-xt-wallet) or [Phoenix Wallet](https://phoenix-wallet.rocks/)

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
4. Verify SmartC output using [smartc-signum-compiler](https://www.npmjs.com/package/smartc-signum-compiler) or build [smartc-web-ui](https://smartc.signum-network.dev/) locally

## Requirements

- Python 3.10+
- No external dependencies (stdlib only)

## License

MIT

## References

- [Signum Blockchain](https://signum.network/)
- [SmartC Compiler Documentation](https://github.com/deleterium/SmartC)
- [SmartC Web UI (source)](https://smartc.signum-network.dev/)
- [SmartC npm Package](https://www.npmjs.com/package/smartc-signum-compiler)
- [SC-Simulator (debugger)](https://github.com/deleterium/SC-Simulator)
- [Signum SmartC Testbed (automated testing)](https://github.com/ohager/signum-smartc-testbed)
- [Signum Wallet - XT (browser extension)](https://github.com/signum-network/signum-xt-wallet)
- [Phoenix Wallet (cross-platform)](https://phoenix-wallet.rocks/)

**Note:** SmartC Web IDE at deleterium.info is no longer available. Use npm package or build from source instead.
