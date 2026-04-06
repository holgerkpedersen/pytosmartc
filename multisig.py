# multisig.py - Simple multi-signature wallet

# State variables
owner1 = sender()
owner2 = 0
owner3 = 0
required_signatures = 2

# Transaction variables
tx_to = ""
tx_amount = 0
tx_approved_by_owner1 = 0
tx_approved_by_owner2 = 0
tx_approved_by_owner3 = 0
tx_executed = 0

def setup_owners(owner2_addr, owner3_addr):
    """Setup the three owners (run once)"""
    if sender() == owner1:
        owner2 = owner2_addr
        owner3 = owner3_addr
        emit("Setup", {
            "owner1": owner1,
            "owner2": owner2,
            "owner3": owner3
        })
        return 1
    else:
        emit("Error", {"message": "Only owner1 can setup"})
        return 0

def propose_transaction(to, amount):
    """Propose a new transaction"""
    current_sender = sender()
    
    # Reset approvals
    tx_to = to
    tx_amount = amount
    tx_approved_by_owner1 = 0
    tx_approved_by_owner2 = 0
    tx_approved_by_owner3 = 0
    tx_executed = 0
    
    # Auto-approve if proposer is an owner
    if current_sender == owner1:
        tx_approved_by_owner1 = 1
    elif current_sender == owner2:
        tx_approved_by_owner2 = 1
    elif current_sender == owner3:
        tx_approved_by_owner3 = 1
    else:
        emit("Error", {"message": "Not an owner"})
        return 0
    
    emit("TransactionProposed", {
        "to": to,
        "amount": amount,
        "proposer": current_sender
    })
    return 1

def approve_transaction():
    """Approve the current transaction"""
    current_sender = sender()
    
    if tx_executed == 1:
        emit("Error", {"message": "Transaction already executed"})
        return 0
    
    # Record approval
    if current_sender == owner1:
        tx_approved_by_owner1 = 1
    elif current_sender == owner2:
        tx_approved_by_owner2 = 1
    elif current_sender == owner3:
        tx_approved_by_owner3 = 1
    else:
        emit("Error", {"message": "Not an owner"})
        return 0
    
    # Count approvals
    approval_count = tx_approved_by_owner1 + tx_approved_by_owner2 + tx_approved_by_owner3
    
    emit("Approval", {
        "approver": current_sender,
        "total_approvals": approval_count,
        "required": required_signatures
    })
    
    # Execute if enough approvals
    if approval_count >= required_signatures:
        transfer("SIGNA", tx_to, tx_amount)
        tx_executed = 1
        
        emit("TransactionExecuted", {
            "to": tx_to,
            "amount": tx_amount,
            "approvals": approval_count
        })
        return 1
    
    return 0

def get_approval_status():
    """Check current approval status - return numeric code"""
    # Count approvals: 0 = no approvals, 1-3 = some approvals, 4 = executed
    approval_count = tx_approved_by_owner1 + tx_approved_by_owner2 + tx_approved_by_owner3
    if tx_executed == 1:
        return 4
    elif approval_count >= required_signatures:
        return 3
    else:
        return approval_count