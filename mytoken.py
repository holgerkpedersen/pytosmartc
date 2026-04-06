# token.py - Basic ERC20-like token on Signum

# State variables
name = "MyToken"
symbol = "MTK"
decimals = 8
total_supply = 1000000
owner = sender()

# Initialize balances
set("balance_" + owner, total_supply)
set("total_supply", total_supply)

def transfer(to, amount):
    """Transfer tokens to another address"""
    sender_addr = sender()
    sender_balance = get("balance_" + sender_addr)
    
    if sender_balance >= amount:
        # Update balances
        new_sender_balance = sender_balance - amount
        set("balance_" + sender_addr, new_sender_balance)
        
        receiver_balance = get("balance_" + to)
        new_receiver_balance = receiver_balance + amount
        set("balance_" + to, new_receiver_balance)
        
        # Emit event
        emit("Transfer", {
            "from": sender_addr,
            "to": to,
            "amount": amount
        })
        return 1
    else:
        emit("Error", {"message": "Insufficient balance"})
        return 0

def balance_of(address):
    """Check token balance of an address"""
    return get("balance_" + address)

def mint(to, amount):
    """Mint new tokens (only owner)"""
    if sender() == owner:
        current_supply = get("total_supply")
        new_supply = current_supply + amount
        set("total_supply", new_supply)
        
        current_balance = get("balance_" + to)
        new_balance = current_balance + amount
        set("balance_" + to, new_balance)
        
        emit("Mint", {"to": to, "amount": amount})
        return 1
    else:
        emit("Error", {"message": "Only owner can mint"})
        return 0

def burn(amount):
    """Burn tokens from sender's balance"""
    sender_addr = sender()
    sender_balance = get("balance_" + sender_addr)
    
    if sender_balance >= amount:
        new_balance = sender_balance - amount
        set("balance_" + sender_addr, new_balance)
        
        current_supply = get("total_supply")
        new_supply = current_supply - amount
        set("total_supply", new_supply)
        
        emit("Burn", {"from": sender_addr, "amount": amount})
        return 1
    else:
        emit("Error", {"message": "Insufficient balance to burn"})
        return 0