# lottery.py - Simple lottery contract

# State variables
owner = sender()
ticket_price = 10
total_tickets = 0
lottery_active = 1
draw_block = 0
winner = 0

def start_lottery(duration_blocks):
    """Start a new lottery round"""
    if sender() == owner:
        current_block = block_height()
        draw_block = current_block + duration_blocks
        lottery_active = 1
        total_tickets = 0
        winner = 0
        
        emit("LotteryStarted", {
            "draw_block": draw_block,
            "ticket_price": ticket_price
        })
        return 1
    else:
        emit("Error", {"message": "Only owner can start"})
        return 0

def buy_ticket():
    """Buy a lottery ticket"""
    if lottery_active == 0:
        emit("Error", {"message": "Lottery not active"})
        return 0
    
    current_block = block_height()
    if current_block >= draw_block:
        lottery_active = 0
        emit("Error", {"message": "Lottery ended"})
        return 0
    
    # Check payment
    paid_amount = tx_amount()
    if paid_amount < ticket_price:
        emit("Error", {"message": "Insufficient payment"})
        return 0
    
    # Record ticket
    buyer = sender()
    ticket_number = total_tickets + 1
    set("ticket_" + str(ticket_number), buyer)
    total_tickets = total_tickets + 1
    
    emit("TicketPurchased", {
        "buyer": buyer,
        "ticket_number": ticket_number,
        "total_tickets": total_tickets
    })
    
    # Refund excess payment
    if paid_amount > ticket_price:
        refund_amount = paid_amount - ticket_price
        transfer("SIGNA", buyer, refund_amount)
    
    return 1

def draw_winner():
    """Draw the lottery winner"""
    if lottery_active == 1:
        current_block = block_height()
        if current_block < draw_block:
            emit("Error", {"message": "Draw not ready"})
            return 0
        
        lottery_active = 0
    
    if total_tickets == 0:
        emit("Error", {"message": "No tickets sold"})
        return 0
    
    if winner != 0:
        emit("Error", {"message": "Winner already drawn"})
        return 0
    
    # Use block hash for randomness (simplified)
    # In real implementation, you'd use a better source of randomness
    random_value = block_height()
    winning_number = random_value % total_tickets + 1
    winner = get("ticket_" + str(winning_number))
    
    # Prize is all collected funds (ticket_price * total_tickets)
    prize_amount = ticket_price * total_tickets
    transfer("SIGNA", winner, prize_amount)
    
    emit("WinnerDrawn", {
        "winner": winner,
        "ticket_number": winning_number,
        "prize": prize_amount
    })
    
    return 1

def get_ticket_count():
    """Get number of tickets sold"""
    return total_tickets