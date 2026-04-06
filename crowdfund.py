# crowdfund.py - Crowdfunding campaign contract

# Campaign parameters
owner = sender()
goal_amount = 0
deadline_block = 0
total_raised = 0
campaign_active = 1

def setup_campaign(goal, duration_blocks):
    """Setup crowdfunding campaign"""
    if sender() == owner:
        goal_amount = goal
        current_block = block_height()
        deadline_block = current_block + duration_blocks
        campaign_active = 1
        total_raised = 0
        
        emit("CampaignStarted", {
            "goal": goal,
            "deadline": deadline_block,
            "duration": duration_blocks
        })
        return 1
    else:
        emit("Error", {"message": "Only owner can setup"})
        return 0

def contribute():
    """Contribute to the campaign"""
    contribution_amount = tx_amount()
    current_block = block_height()
    
    if campaign_active == 0:
        emit("Error", {"message": "Campaign ended"})
        return 0
    
    if current_block > deadline_block:
        campaign_active = 0
        emit("Error", {"message": "Deadline passed"})
        return 0
    
    # Record contribution
    contributor = sender()
    current_contribution = get("contribution_" + contributor)
    new_contribution = current_contribution + contribution_amount
    set("contribution_" + contributor, new_contribution)
    
    # Update total raised
    total_raised = total_raised + contribution_amount
    
    emit("Contribution", {
        "contributor": contributor,
        "amount": contribution_amount,
        "total_raised": total_raised
    })
    
    # Check if goal reached
    if total_raised >= goal_amount:
        campaign_active = 0
        emit("GoalReached", {"total_raised": total_raised})
    
    return 1

def withdraw_refund():
    """Withdraw refund if goal not reached"""
    current_block = block_height()
    
    if campaign_active == 0:
        emit("Error", {"message": "Campaign ended"})
        return 0
    
    if current_block <= deadline_block:
        emit("Error", {"message": "Campaign still active"})
        return 0
    
    # Refund contributor
    contributor = sender()
    contribution_amount = get("contribution_" + contributor)
    
    if contribution_amount > 0:
        transfer("SIGNA", contributor, contribution_amount)
        set("contribution_" + contributor, 0)
        
        emit("Refund", {
            "contributor": contributor,
            "amount": contribution_amount
        })
        return 1
    else:
        emit("Error", {"message": "No contributions found"})
        return 0

def withdraw_funds():
    """Withdraw funds if goal reached (owner only)"""
    current_block = block_height()
    
    if campaign_active == 1:
        emit("Error", {"message": "Campaign still active"})
        return 0
    
    if sender() != owner:
        emit("Error", {"message": "Only owner can withdraw"})
        return 0
    
    if total_raised >= goal_amount:
        transfer("SIGNA", owner, total_raised)
        emit("FundsWithdrawn", {"amount": total_raised})
        return 1
    else:
        emit("Error", {"message": "Goal not reached"})
        return 0

def get_campaign_status():
    """Get current campaign status - return numeric code"""
    # 0 = inactive, 1 = active, 2 = goal reached, 3 = deadline passed
    if campaign_active == 1:
        return 1
    elif total_raised >= goal_amount:
        return 2
    else:
        current_block = block_height()
        if current_block > deadline_block:
            return 3
        return 0