# vault.py - Time-locked vault contract

# State variables
owner = sender()
lock_amount = 0
release_block = 0
withdrawn = 0

def lock(amount, lock_blocks):
    """Lock tokens until a certain block height"""
    sender_addr = sender()
    
    if sender_addr == owner:
        lock_amount = amount
        current_block = block_height()
        release_block = current_block + lock_blocks
        withdrawn = 0
        
        # Transfer tokens to contract
        transfer("SIGNA", sender_addr, amount)
        
        emit("Locked", {
            "amount": amount,
            "release_block": release_block,
            "duration": lock_blocks
        })
        return 1
    else:
        emit("Error", {"message": "Only owner can lock"})
        return 0

def withdraw():
    """Withdraw locked tokens after release time"""
    current_block = block_height()
    
    if withdrawn == 0:
        if current_block >= release_block:
            # Transfer back to owner
            transfer("SIGNA", owner, lock_amount)
            withdrawn = 1
            
            emit("Withdrawn", {
                "amount": lock_amount,
                "block": current_block
            })
            return 1
        else:
            remaining_blocks = release_block - current_block
            emit("Error", {
                "message": "Still locked",
                "remaining_blocks": remaining_blocks
            })
            return 0
    else:
        emit("Error", {"message": "Already withdrawn"})
        return 0

def get_status():
    """Check vault status"""
    current_block = block_height()
    
    if withdrawn == 1:
        return "withdrawn"
    elif current_block >= release_block:
        return "ready"
    else:
        remaining = release_block - current_block
        return "locked:" + str(remaining)