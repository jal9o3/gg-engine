import logging, copy, random, json, os, ctypes, csv, time, itertools

from ctypes import c_int, c_double

from collections import deque

# Configure the logging
logging.basicConfig(level=logging.WARNING)

# World constants
from world_constants import *

# Infostate related functions
from infostate_logic import *

# Public belief state related functions
from pbs_logic import *



# Determine if the current state is a terminal state
def is_terminal(board, annotation):

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    # If either of the flags have been captured
    if not any(FLAG in _ for _ in board) or \
       not any(SPY + FLAG in _ for _ in board):
        return True
    
    # If the blue flag is on the other side of the board
    if FLAG in board[-1]:
        # If flag has already survived a turn
        if annotation[WAITING_BLUE_FLAG]:
            return True
        else:
            flag_col = board[-1].index(FLAG) # Get the flag's column number
            return has_none_adjacent(flag_col, board[-1])

    # Do the same checking for the red flag
    if SPY + FLAG in board[0]:
        if annotation[WAITING_RED_FLAG]:
            return True
        else:
            flag_col = board[0].index(SPY + FLAG)
            return has_none_adjacent(flag_col, board[0])

    # If none of the checks have been passed, it is not a terminal state
    return False

# Measure overall reward of terminal states
# 1 is a blue win, -1 is a red win
def reward(board, annotation):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    # A non-terminal state is not eligible of assessment
    if not is_terminal(board, annotation):
        logger.debug("state is not terminal")
        return None
    
    # Blue flag captured
    elif not any(FLAG in _ for _ in board):
        return -1
    
    # Red flag captured
    elif not any(SPY + FLAG in _ for _ in board):
        return 1

    # Blue flag reaches red side
    elif FLAG in board[-1]:
        logger.debug("blue flag in red side")
        # If flag has already survived a turn
        if annotation[WAITING_BLUE_FLAG]:
            return 1
        else:
            flag_col = board[-1].index(FLAG) # Get the flag's column number
            if has_none_adjacent(flag_col, board[-1]):
                return 1

    # Red flag reaches red side
    if SPY + FLAG in board[0]:
        if annotation[WAITING_RED_FLAG]:
            return -1
        else:
            flag_col = board[0].index(SPY + FLAG)
            if has_none_adjacent(flag_col, board[0]):
                return -1
    
# Obtain all possible actions for each state
def actions(board, annotation):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    current_player = annotation[CURRENT_PLAYER]
    # Set ranges of piece designations
    range_start, range_end = (
        (FLAG, SPY) if current_player == BLUE else (SPY + FLAG, SPY + SPY)
    )   

    def is_valid(square):
        return not (range_start <= square <= range_end) or square == BLANK

    moves = []
    # Iterate over every square of the board
    for row in range(ROWS):
        for column in range(COLUMNS):
            square = board[row][column]
            # Check for a piece that belongs to the current player
            if square <= range_end and square >= range_start:
                # Check for allied pieces in adjacent squares:
                if row != ROWS - 1: # UP
                    if is_valid(board[row + 1][column]):
                        moves.append(f"{row}{column}{row + 1}{column}")
                if row != 0: # DOWN
                    if is_valid(board[row - 1][column]):
                        moves.append(f"{row}{column}{row - 1}{column}")
                if column != COLUMNS - 1: # RIGHT
                    if is_valid(board[row][column + 1]):
                        moves.append(f"{row}{column}{row}{column + 1}")
                if column != 0: # LEFT
                    if is_valid(board[row][column - 1]):
                        moves.append(f"{row}{column}{row}{column - 1}")
    return moves            

def transition(board, annotation, action):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    def move_piece(start_row, start_col, end_row, end_col):
       new_board[end_row][end_col] = board[start_row][start_col]
       new_board[start_row][start_col] = BLANK

    def handle_challenges(challenger_value, target_value):
        # Edge case where PRIVATE defeats SPY
        if (challenger_value == PRIVATE and target_value == SPY):
            move_piece(start_row, start_col, end_row, end_col)
            return
        elif (challenger_value == SPY and target_value == PRIVATE):
            new_board[start_row][start_col] # remove losing attacker
            return
        # Stronger piece or flag challenge
        if (challenger_value > target_value
            or (challenger_value == FLAG and target_value == FLAG)):            
            move_piece(start_row, start_col, end_row, end_col)
        elif challenger_value < target_value:
            new_board[start_row][start_col] = BLANK # remove losing attacker
        else:
            # Remove both in tie
            new_board[start_row][start_col] = BLANK
            new_board[end_row][end_col] = BLANK
    
    new_board, new_annotation = copy.deepcopy(board), copy.deepcopy(annotation)

    # Obtain indices of starting and destination squares
    start_row, start_col, end_row, end_col = map(int, action)

    current_player = annotation[CURRENT_PLAYER]
    range_start = FLAG if current_player == BLUE else FLAG + SPY
    range_end = SPY if current_player == BLUE else SPY + SPY

    # Check if starting square's piece belongs to current player
    if not (board[start_row][start_col] != BLANK
            and range_start <= board[start_row][start_col] <= range_end):
        return None
    
    # Check if destination square's piece does not belong to the current player
    if (board[end_row][end_col] != BLANK
        and range_start <= board[end_row][end_col] <= range_end):
        return None

    # If the destination square is blank, move selected piece to it
    if board[end_row][end_col] == BLANK:
        move_piece(start_row, start_col, end_row, end_col)
    elif current_player == BLUE: # Handle challenges
        opponent_value = board[end_row][end_col] - SPY
        handle_challenges(board[start_row][start_col], opponent_value)
    elif current_player == RED:
        own_value = board[start_row][start_col] - SPY
        handle_challenges(own_value, board[end_row][end_col])
        
    new_annotation[CURRENT_PLAYER] = RED if current_player == BLUE else BLUE
    # If the blue flag reaches the other side
    if (FLAG in board[-1] and not annotation[WAITING_BLUE_FLAG]
        and not has_none_adjacent(board[-1].index(FLAG), board[-1])):
        new_annotation[WAITING_BLUE_FLAG] = 1
    # Check for the red flag
    elif (SPY + FLAG in board[0] and not annotation[WAITING_RED_FLAG]
          and not has_none_adjacent(board[0].index(SPY + FLAG), board[0])):
        new_annotation[WAITING_RED_FLAG] = 1
    return (new_board, new_annotation)          

# Procedure for checking adjacent enemy pieces in waiting flags
def has_none_adjacent(flag_col, nrow): # nrow is either the first or last row
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # If not at the left or rightmost edge of the board
    if flag_col != 0 and flag_col != COLUMNS - 1:
        # Check both squares to the left and right
        if not nrow[flag_col - 1] and not nrow[flag_col + 1]:
            return True
    elif flag_col == 0 and not nrow[flag_col + 1]:
        # If flag is at the first column and the square next to it is empty
        return True
    elif flag_col == COLUMNS - 1 and not nrow[flag_col - 1]:
        # If flag is at the last column and the square before it is empty
        return True
    else:
        return False


# Give utility estimates to nonterminal board estimates
# NOTE: Reward is from the perspective of BLUE (negative values are pro-RED)
def reward_estimate(board, annotation):
    # Initialize the utility value
    utility = 0

    # Estimated rewards for features
    capture_reward = 0.40
    push_reward = 0.0375 # 0.30/8
    flag_safety_reward = 0.02 # 0.30/(ROWS - 1 + COLUMNS - 1)

    total_firepower = 145 # Sum of rankings of all pieces in an army
    blue_firepower = 0
    red_firepower = 0
    
    # Rewards for captured and pushed pieces
    blue_pieces = 0
    red_pieces = 0
    # Count BLUE and RED pieces
    for i, row in enumerate(board):
        for j, square in enumerate(row):
            # Check if the piece is BLUE or RED
            if FLAG <= square <= SPY:
                # blue_pieces +=1
                blue_firepower += square
                # Reward based on the piece's row
                utility += i*push_reward
            elif FLAG + SPY <= square <= SPY + SPY:
                # red_pieces += 1
                red_firepower = square - SPY
                # Reward based on the piece's row
                utility += -((ROWS-i)*push_reward)
    
    # For each missing piece, reward the enemy
    # missing_blue = INITIAL_ARMY - blue_pieces
    # missing_red = INITIAL_ARMY - red_pieces
    # utility += -(missing_blue*capture_reward)
    # utility += missing_red*capture_reward

    # Reward the player based on their remaining firepower
    utility += (blue_firepower/total_firepower)*capture_reward
    utility += -((red_firepower/total_firepower)*capture_reward)


    # Reward estimates for flag safety
    blue_flag = find_integer(board, FLAG)
    red_flag = find_integer(board, FLAG + SPY)
    nearest_red = find_nearest_in_range_bfs(
        board, blue_flag[0], blue_flag[1], FLAG + SPY, SPY*2)
    nearest_blue = find_nearest_in_range_bfs(
        board, red_flag[0], red_flag[1], FLAG, SPY)
    # Calculate the Manhattan distance of nearest enemy to each flag
    blue_manhattan = abs(
        nearest_red[0] - blue_flag[0]) + abs(nearest_red[1] - blue_flag[1])
    red_manhattan = abs(
        nearest_blue[0] - red_flag[0]) + abs(nearest_blue[1] - red_flag[1])
    
    utility += blue_manhattan*flag_safety_reward + 0.30
    utility += -(red_manhattan*flag_safety_reward + 0.30)

    # Find the value of the flag's "protector"
    blue_protector = max_in_range(board, blue_flag, nearest_red, PRIVATE, SPY)
    red_protector = max_in_range(board, red_flag, nearest_blue, 
                                 PRIVATE + SPY, SPY*2) - SPY
    utility += blue_protector*flag_safety_reward
    utility += -(red_protector*flag_safety_reward)

    # Measure flag "freedom"
    # Check count of pieces in the flag's direct path
    blue_flagblocks = count_nonzero_neighbors(board, blue_flag[0], blue_flag[1])
    red_flagblocks = count_nonzero_neighbors(board, red_flag[0], red_flag[1])
    # If the flag is not at the starting edge, check neighbors of square behind it
    if blue_flag[0] > 0:
        blue_flagblocks += count_nonzero_neighbors(board, blue_flag[0] - 1, blue_flag[1])
    if red_flag[0] < 7:
        red_flagblocks += count_nonzero_neighbors(board, red_flag[0] + 1, red_flag[1])

    utility += -(blue_flagblocks*flag_safety_reward)
    utility += red_flagblocks*flag_safety_reward


    return utility

"""
Example usage
matrix = [
    [1, 0, 3],
    [0, 5, 0],
    [7, 0, 9]
]
row, col = 1, 1  # position (1, 1) in the matrix

print(count_nonzero_neighbors(matrix, row, col))  # Output will be 0
"""
def count_nonzero_neighbors(matrix, row, col):
    rows = len(matrix)
    cols = len(matrix[0])
    nonzero_count = 0

    # Define the directions for up, down, left, and right
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    for dr, dc in directions:
        new_row, new_col = row + dr, col + dc
        # Check if the new position is within bounds
        if 0 <= new_row < rows and 0 <= new_col < cols:
            if matrix[new_row][new_col] != 0:
                nonzero_count += 1

    return nonzero_count


"""
Example usage
matrix = [
    [10, 20, 30],
    [40, 50, 60],
    [70, 80, 90]
]
target = 50

result = find_integer(matrix, target)
print(result)  # Output: (1, 1) because 50 is located at row 1, column 1
"""
def find_integer(matrix, target):
    for row in range(len(matrix)):
        for col in range(len(matrix[row])):
            if matrix[row][col] == target:
                return (row, col)
    return None

"""
Example usage
matrix = [
    [10, 20, 30],
    [40, 50, 60],
    [70, 80, 90]
]
target_row = 1
target_column = 1
MIN = 35
MAX = 75

result = find_nearest_in_range_bfs(matrix, target_row, target_column, MIN, MAX)
print(result)  # Output: (2, 0) because 70 is the nearest element in range [35, 75] 
               # to element (1, 1)
"""
def find_nearest_in_range_bfs(matrix, target_row, target_column, MIN, MAX):
    def is_in_range(value):
        return MIN <= value <= MAX
    
    rows = len(matrix)
    cols = len(matrix[0])
    visited = [[False] * cols for _ in range(rows)]
    directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]
    
    queue = deque([(target_row, target_column, 0)])  # (row, column, distance)
    visited[target_row][target_column] = True
    
    while queue:
        r, c, dist = queue.popleft()
        
        if is_in_range(matrix[r][c]):
            return (r, c)
        
        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc]:
                visited[nr][nc] = True
                queue.append((nr, nc, dist + 1))
    
    return None

"""
Example Usage
matrix = [
    [1, 2, 3],
    [4, 5, 6],
    [7, 8, 9]
]
square_a = (0, 0)  # Row 0, Column 0
square_b = (2, 2)  # Row 2, Column 2
min_val = 4
max_val = 8

result = max_in_range(matrix, square_a, square_b, min_val, max_val)
print(f"Maximum value in range [{min_val}, {max_val}]: {result}")
"""
def max_in_range(matrix, square_a, square_b, min_val, max_val):
    # Extract the row and column indices
    row1, col1 = square_a
    row2, col2 = square_b

    # Determine the bounds of the sub-matrix
    top = min(row1, row2)
    bottom = max(row1, row2)
    left = min(col1, col2)
    right = max(col1, col2)

    # Flatten the sub-matrix using itertools.chain
    flattened_sub_matrix = itertools.chain.from_iterable(
        row[left:right + 1] for row in matrix[top:bottom + 1]
    )
    flattened_list = list(flattened_sub_matrix)
    # print(flattened_list)

    # Filter values within the range [min_val, max_val]
    filtered_values = [value for value in flattened_list if min_val <= value <= max_val]
    # print(filtered_values)
    

    # Find the maximum value, or return None if no values are in range
    return max(filtered_values, default=0)

# Adapt counterfactual regret minimization to GG
# For external sampling, set traverser to BLUE or RED
# Obtained policies can be stored in a dictionary via the policy_table parameter
# Set policy_table to None if policies will not be stored
def cfr(board, annotation, blue_probability, red_probability,
        current_depth, max_depth, turn_number=0, traverser=0,
        policy_table=None, utility_table=None,
        blue_infostate=None, blue_infostate_annotation=None,
        red_infostate=None, red_infostate_annotation=None,
        utility_model=None, policy_model=None):

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    player = annotation[CURRENT_PLAYER]

    # Obtain the current player's infostate
    if player == BLUE:
        relevant_infostate, relevant_infostate_annotation = blue_infostate, blue_infostate_annotation
    else:
        relevant_infostate, relevant_infostate_annotation = red_infostate, red_infostate_annotation

    # Convert the infostate to a string for storage in the dictionary
    if policy_table != None:
        infostate_key = infostate_to_string(relevant_infostate, relevant_infostate_annotation)

    # Return payoff for 'terminal' states
    if ((current_depth == max_depth and is_terminal(board, annotation))
         or is_terminal(board, annotation)):
        logger.setLevel(logging.DEBUG)
        if player == BLUE:
            # Store the utility in the utility table
            if utility_table != None:
                utility_table[infostate_key] = reward(board, annotation)
            return reward(board, annotation), []
        else:
            # Store the utility in the utility table
            if utility_table != None:
                utility_table[infostate_key] = -reward(board, annotation)
            return -reward(board, annotation), []
    elif current_depth == max_depth and not is_terminal(board, annotation):
        # if utility_model != None:
        #   # Convert infostate to list
        #   infolist = infostate_key.split()
        #   # Convert list to np array
        #   infoarray = np.array(infolist, dtype=np.float32)
        #   # Convert np array to Pytorch tensor
        #   infotensor = torch.tensor(infoarray)
        #   infotensor = infotensor.to(device)
        #   # Reshape the tensor to what is expected of the utility network
        #   infotensor = infotensor.view(1, -1)
        #   return utility_model(infotensor).item(), [] # Obtain the utility estimate
        # else:
        #   return 0, []
        if player == BLUE:
            return reward_estimate(board, annotation), []
        else:
            return -reward_estimate(board, annotation), []


    # Initialize strategy
    valid_actions = actions(board, annotation)
    actions_n = len(valid_actions)

    # Obtain policy from policy table if any
    if policy_table != None:
        if infostate_key in policy_table:
            strategy = policy_table[infostate_key][0]
        # Use the policy network to obtain probability estimates
        elif policy_model != None:
          # Concatenate the infostate strings with the move representations
          # Iterate through the actions
          strategy = [0.0 for i in range(actions_n)] # Prepare empty strategy
          for i, action in enumerate(valid_actions):
            infostate_and_action = ""
            infostate_and_action += infostate_key # Infostate representation

            for j in range(4): # Length of an action representation
                infostate_and_action += " " + action[j] # Concatenation

            # Convert concatenated string to list
            concatlist = infostate_and_action.split()
            # Convert list to np array
            concatarray = np.array(concatlist, dtype=np.float32)
            # Convert np array to Pytorch tensor
            concatensor = torch.tensor(concatarray)
            concatensor = concatensor.to(device)
            # Reshape the tensor to what is expected of the policy network
            concatensor = concatensor.view(1, -1)
            probability = policy_model(concatensor) # Obtain the probability estimate
            strategy[i] = probability.item() # Store the estimate in the strategy

            # Sanitize the strategy
            for i in range(len(strategy)):
              if strategy[i] < 0:
                strategy[i] = 0
            if sum(strategy) <= 0:
              strategy = [1.0/actions_n for i in range(actions_n)] # Uniform strategy
        else:
            strategy = [1.0/actions_n for i in range(actions_n)] # Uniform strategy
    else:
        strategy = [1.0/actions_n for i in range(actions_n)] # Uniform strategy
    regret_sum = [0.0 for i in range(actions_n)]

    # Initialize action utilities
    util = [0.0 for i in range(actions_n)]
    # Initialize node utility
    node_util = 0

    # For external sampling
    # If the current player is not the traverser, just sample a move
    if traverser != 0 and player != traverser:
        # Set negative weights to zero to avoid errors
        for a, action in enumerate(strategy):
            if action < 0:
                strategy[a] = 0
        # Sample an action
        action = random.choices(valid_actions, weights=strategy, k=1)[0]
        next_board, next_annotation = transition(board, annotation, action)
        action_result = get_result(board, annotation, action, next_board, next_annotation)
        next_blue_infostate, next_blue_infostate_annotation = private_observation(blue_infostate, blue_infostate_annotation, action, action_result)
        next_red_infostate, next_red_infostate_annotation = private_observation(red_infostate, red_infostate_annotation, action, action_result)

        # Call CFR on the action
        if player == BLUE:
            result = cfr(next_board, next_annotation,
                red_probability * strategy[valid_actions.index(action)], blue_probability,
                current_depth + 1, max_depth, traverser=traverser, policy_table=policy_table, utility_table=utility_table,
                blue_infostate=next_blue_infostate, blue_infostate_annotation=next_blue_infostate_annotation,
                red_infostate=next_red_infostate, red_infostate_annotation=next_red_infostate_annotation,
                utility_model=utility_model, policy_model=policy_model)
            util[valid_actions.index(action)] = -(result[0])
        else:
            result = cfr(next_board, next_annotation,
                blue_probability, red_probability * strategy[valid_actions.index(action)],
                current_depth + 1, max_depth, traverser=traverser, policy_table=policy_table, utility_table=utility_table,
                blue_infostate=next_blue_infostate, blue_infostate_annotation=next_blue_infostate_annotation,
                red_infostate=next_red_infostate, red_infostate_annotation=next_red_infostate_annotation,
                utility_model=utility_model, policy_model=policy_model)
            util[valid_actions.index(action)] = -(result[0])

        # Calculate node utility
        node_util += strategy[valid_actions.index(action)] * util[valid_actions.index(action)]
    elif traverser == 0 or traverser == player:
        # Iterate over children nodes and recursively call cfr
        for a, action in enumerate(valid_actions):
            next_board, next_annotation = transition(board, annotation, action)
            action_result = get_result(board, annotation, action, next_board, next_annotation)
            next_blue_infostate, next_blue_infostate_annotation = private_observation(blue_infostate, blue_infostate_annotation, action, action_result)
            next_red_infostate, next_red_infostate_annotation = private_observation(red_infostate, red_infostate_annotation, action, action_result)

            if player == BLUE:
                result = cfr(next_board, next_annotation,
                    red_probability * strategy[a], blue_probability,
                    current_depth + 1, max_depth, traverser=traverser, policy_table=policy_table, utility_table=utility_table,
                    blue_infostate=next_blue_infostate, blue_infostate_annotation=next_blue_infostate_annotation,
                    red_infostate=next_red_infostate, red_infostate_annotation=next_red_infostate_annotation,
                    utility_model=utility_model, policy_model=policy_model)
                util[a] = -(result[0])
            else:
                result = cfr(next_board, next_annotation,
                    blue_probability, red_probability * strategy[a],
                    current_depth + 1, max_depth, traverser=traverser, policy_table=policy_table, utility_table=utility_table,
                    blue_infostate=next_blue_infostate, blue_infostate_annotation=next_blue_infostate_annotation,
                    red_infostate=next_red_infostate, red_infostate_annotation=next_red_infostate_annotation,
                    utility_model=utility_model, policy_model=policy_model)
                util[a] = -(result[0])

            # Calculate node utility
            node_util += strategy[a] * util[a]

    # Calculate regret sum
    for a, action in enumerate(valid_actions):
        logger.setLevel(logging.DEBUG)
        regret = util[a] - node_util
        regret_sum[a] += (red_probability if player == BLUE else blue_probability) * regret

    # Normalize regret sum to find strategy for this node
    strategy = [0.0 for i in range(actions_n)]
    normalizing_sum = sum(regret_sum)
    for a, action in enumerate(valid_actions):
        if regret_sum[a] > 0:
            normalizing_sum += regret_sum[a]

    for a, action in enumerate(valid_actions):
        if normalizing_sum > 0:
            strategy[a] = regret_sum[a] / normalizing_sum
        else:
            strategy[a] = 1.0 / actions_n

        # Update node utility with regret-matched strategy
        node_util += strategy[a] * util[a]

    # Store the policy in the policy_table
    if policy_table != None and utility_table != None:
        policy_table[infostate_key] = (strategy, valid_actions, turn_number)
        utility_table[infostate_key] = node_util

    # Return node utility
    return node_util, strategy

# Training loop for CFR
def cfr_train(board, annotation, blue_probability, red_probability,
              current_depth, max_depth, turn_number=0, iterations=10,
              policy_table=None, utility_table=None,
              blue_infostate=None, blue_infostate_annotation=None,
              red_infostate=None, red_infostate_annotation=None,
              utility_model=None, policy_model=None):

    start_time = time.time()

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # Print the nearest enemy pieces to the flags
    # blue_flag = find_integer(board, FLAG)
    # red_flag = find_integer(board, SPY + FLAG)
    # print("Nearest to BLUE flag:")
    # print(find_nearest_in_range_bfs(board, blue_flag[0], blue_flag[1], FLAG + SPY, SPY*2))
    # print("Nearest to RED flag:")
    # print(find_nearest_in_range_bfs(board, red_flag[0], red_flag[1], FLAG, SPY))

    traverser = BLUE
    utility_sum = 0.0
    strategy_sum = [0.0 for i in range(len(actions(board, annotation)))]

    for i in range(iterations):
        # start_time = time.time()
        util, strategy = cfr(board, annotation, blue_probability, red_probability,
            current_depth, max_depth, policy_table=policy_table, utility_table=utility_table,
            blue_infostate=blue_infostate, blue_infostate_annotation=blue_infostate_annotation,
            red_infostate=red_infostate, red_infostate_annotation=red_infostate_annotation,
            utility_model=utility_model, policy_model=policy_model, turn_number=turn_number)
        # end_time = time.time()
        # print(f"Runtime: {end_time - start_time} seconds")

        # Add strategy to strategy sum
        for i in range(len(actions(board, annotation))):
            if strategy[i] > 0:
                strategy_sum[i] += strategy[i]
        # Add utility to utility sum
        utility_sum += util
        # Switch to next traverser
        traverser = RED if traverser == BLUE else BLUE

    # Normalize the strategy sum
    accumulated = 0.0
    for i in range(len(actions(board, annotation))):
        accumulated += strategy_sum[i]
    for i in range(len(actions(board, annotation))):
        strategy_sum[i] /= accumulated
    # Calculate the average utility
    average_utility = utility_sum / iterations

    end_time = time.time()
    print(f"Runtime: {end_time - start_time} seconds")

    return average_utility, strategy_sum

# Represent initial information states for BLUE and RED
# 42 ROWS (21 pieces each) by 19 COLS (Player, p(1...15), row, col, captured)
def initial_infostate(board, player):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.WARNING)
    
    # Initialize blank matrix for the infostate
    infostate = [[BLANK for _ in range(INFOCOLS)] for _ in range(INFOROWS)]
    infostate_annotation = [BLUE, 0, player]

    range_start, range_end = (
        (FLAG, SPY) if player == BLUE else (FLAG + SPY, 2*SPY)
    )
    # # Obtain initial probabilities
    range_offset = 0 if player == BLUE else SPY # for finding the correct columns
    for piece in range(INITIAL_ARMY):
        for col in range(INFOCOLS):
            if col == PLAYER:
                infostate[piece][col] = RED if player == BLUE else BLUE
            # elif range_start - range_offset <= col <= range_end - range_offset:
            #     if col == PRIVATE:
            #         infostate[piece][col] = 6/INITIAL_ARMY
            #     elif col == SPY:
            #         infostate[piece][col] = 2/INITIAL_ARMY
            #     else:
            #         infostate[piece][col] = 1/INITIAL_ARMY
    piece_n = 0
    # Add locations
    for row in range(ROWS):
        for column in range(COLUMNS):
            # Locations of opponent's pieces
            if (piece_n < INITIAL_ARMY and
                not (range_start <= board[row][column] <= range_end)
                and board[row][column] != BLANK):
                infostate[piece_n][ROW] = row
                infostate[piece_n][COLUMN] = column
                # Set initial value range (for evidence pruning)
                infostate[piece_n][RANGE_BOT] = FLAG
                infostate[piece_n][RANGE_TOP] = SPY
                piece_n += 1
    # Restart loop to obtain the player's piece locations
    for row in range(ROWS):
        for column in range(COLUMNS):
            if (piece_n >= INITIAL_ARMY and
                    range_start <= board[row][column] <= range_end
                    and board[row][column] != BLANK):
                value = (
                    board[row][column] if player == BLUE
                    else board[row][column] - SPY
                ) # calculate actual value of the piece
                logger.debug(f"{piece_n} {value}")
                infostate[piece_n][PLAYER] = player
                # infostate[piece_n][value] = 1
                infostate[piece_n][ROW] = row
                infostate[piece_n][COLUMN] = column
                # Possible value range ends are equal for identified pieces
                infostate[piece_n][RANGE_BOT] = value
                infostate[piece_n][RANGE_TOP] = value
                piece_n += 1
    
    return infostate, infostate_annotation

# Represent initial public belief state
def initial_pbs(board):
    # Initialize blank matrix for the infostate
    pbs = [[BLANK for _ in range(PBS_COLS)] for _ in range(PBS_ROWS)]
    pbs_annotation = [BLUE]

    blue_range_start, blue_range_end = FLAG, SPY
    red_range_start, red_range_end = SPY + FLAG, 2*SPY

    piece_n = 0
    # Add locations
    for row in range(ROWS):
        for column in range(COLUMNS):
            # Locations of BLUE's pieces
            if (piece_n < INITIAL_ARMY and
                blue_range_start <= board[row][column] <= blue_range_end
                and board[row][column] != BLANK):
                pbs[piece_n][PBS_PLAYER] = BLUE
                pbs[piece_n][PBS_ROW] = row
                pbs[piece_n][PBS_COLUMN] = column
                piece_n += 1
    # Restart loop to obtain RED's piece locations
    for row in range(ROWS):
        for column in range(COLUMNS):
            if (piece_n >= INITIAL_ARMY and
                    red_range_start <= board[row][column] <= red_range_end
                    and board[row][column] != BLANK):
                pbs[piece_n][PBS_PLAYER] = RED
                pbs[piece_n][PBS_ROW] = row
                pbs[piece_n][PBS_COLUMN] = column
                piece_n += 1
    return pbs, pbs_annotation

def print_board(board, color=False, pov=WORLD):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    def colored(text, color_code):
        return f"\033[{color_code}m{text:2}\033[0m"
    
    print()
    for i, row in enumerate(board):
        print(f"{i:2}", end='  ')
        for j, elem in enumerate(row): 
            if elem == BLANK:
                print(" -", end=' ')
            elif pov == WORLD:
                if color and elem == FLAG:
                    print(colored(elem, "34"), end=' ')  # Blue
                elif color and elem == FLAG + SPY:
                    print(colored(elem, "31"), end=' ')  # Red
                elif elem < 0:  # For board diffs
                    print(colored(abs(elem), "33"), end=' ')  # Yellow
                else:
                    print(f"{elem:2}", end=' ')
            elif pov in {BLIND, BLUE, RED}:
                is_blue_pov = pov in {BLIND, BLUE}
                if elem <= SPY and elem >= FLAG and is_blue_pov: # if piece is blue and pov is blue
                    if color and elem == FLAG and is_blue_pov: # color flag according to pov
                        print(colored(elem, "34"), end=' ')  # Blue
                    else:
                        print(f"{elem:2}", end=' ')
                elif elem <= 2*SPY and elem >= FLAG + SPY and not is_blue_pov:
                    if color and elem == FLAG + SPY and not is_blue_pov:
                        print(colored(elem - SPY, "31"), end=' ')  # Red
                    else:
                        print(f"{elem - SPY:2}", end=' ')
                else:
                    unknown = BLUE_UNKNOWN if is_blue_pov else RED_UNKNOWN
                    print(f"{unknown:2}", end=' ')                    
        print()
    print("\n    ", end='')
    for k in range(COLUMNS):
        print(f"{k:2}", end=' ')
    print()       

# Parameter save_game=True if game data will be saved
# available modes: HUMAN_VS_RANDOM, RANDOM_VS_RANDOM, CFR_VS_CFR
def simulate_game(blue_formation, red_formation, mode=CFR_VS_CFR,
                  cfr=cfr, c=False, save_game=True,
                  utility_model=None, policy_model=None):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # Board for arbiter
    board = [[BLANK for _ in range(COLUMNS)] for _ in range(ROWS)]
    annotation = [BLUE, 0, 0]

    # Boards for both player POVs
    blue_board = [[BLANK for _ in range(COLUMNS)] for _ in range(ROWS)]
    red_board = [[BLANK for _ in range(COLUMNS)] for _ in range(ROWS)]

    # Place pieces on blue board
    i = 0
    for row in range(ROWS-3, ROWS):
        for column in range(COLUMNS):
            if i < len(blue_formation):
                blue_board[row][column] = blue_formation[i]
                i += 1

    # Flip the blue board matrix:
    # Flip the blue board matrix upside down
    blue_board = blue_board[::-1]
    # Flip each blue board row left to right
    blue_board = [row[::-1] for row in blue_board]

    # Place pieces on red board
    i = 0
    for row in range(ROWS-3, ROWS):
        for column in range(COLUMNS):
            if i < len(red_formation):
                if red_formation[i] > 0:
                    red_board[row][column] = red_formation[i] + SPY # take note of this change!
                elif red_formation[i] == 0:
                    red_board[row][column] = red_formation[i]
                i += 1

    # Perform matrix addition
    board = [
        [blue_board[i][j] + red_board[i][j] for j in range(COLUMNS)]
        for i in range(len(board))
        ]

    print_board(board, annotation)

    # Handle game saving
    if save_game:
        # Save the initial board configuration, initial annotation is always the same
        game_data = [board]

    blue_infostate, blue_infostate_annotation = initial_infostate(board, BLUE)
    red_infostate, red_infostate_annotation = initial_infostate(board, RED)

    # pbs, pbs_annotation = initial_pbs(board)

    # Gameplay loop
    # mode = RANDOM_VS_RANDOM
    # mode = HUMAN_VS_RANDOM
    # mode = CFR_VS_CFR
    t = 0
    moves_N = 0 # total number of branches found
    if mode == HUMAN_VS_RANDOM:
        human = random.choice([BLUE, RED])
        print(f"You are player {human}")
    else:
        human = 0

    if save_game:
        move_history = [] # Initialize list of moves

    # C standard library
    libc = ctypes.CDLL("libc.so.6")
    free = libc.free
    free.argtypes = [ctypes.c_void_p]

    # Initialize tables for CFR
    if mode == CFR_VS_CFR:
        policy_table = dict()
        utility_table = dict()

    while not is_terminal(board, annotation):
        print(f"Turn: {t + 1}")

        if mode == RANDOM_VS_RANDOM:
            print_board(board, color=True, pov=WORLD)
            # print_infostate(blue_infostate, blue_infostate_annotation)
            # print_infostate(red_infostate, red_infostate_annotation)
            print_pbs(pbs, pbs_annotation)
        elif mode == HUMAN_VS_RANDOM:
            print_board(board, color=True, pov=human)
            print_pbs(pbs, pbs_annotation)
        elif mode == CFR_VS_CFR:
            # print_infostate(blue_infostate, blue_infostate_annotation)
            # print_infostate(red_infostate, red_infostate_annotation)
            print_board(board, color=True, pov=WORLD)
            pass

        print(f"Player: {annotation[CURRENT_PLAYER]}")
        moves = actions(board, annotation)
        print(moves)
        moves_N += len(moves)
        print(f"Possible Moves: {len(moves)}")
        move = ""
        if mode == HUMAN_VS_RANDOM and annotation[CURRENT_PLAYER] == human:
            while move not in moves:
                move = input("Move: ")
        elif mode == RANDOM_VS_RANDOM:
            move = random.choice(moves)
        elif mode == CFR_VS_CFR:

            if len(moves) <= 6:
                max_depth = 4
            elif len(moves) <= 3:
                max_depth = 8
            else:
                max_depth = 2

            # max_depth *= 2
            # max_depth += 1

            logger.setLevel(logging.DEBUG)
            print(f"Solving to depth {max_depth}...")

            if c:
                # Convert the 2D list to a ctypes array
                board_type = (ctypes.c_int * COLUMNS) * ROWS
                # Ctypes array for annotation
                annotation_type = (ctypes.c_int * 3)

                c_board = board_type()
                c_annotation = annotation_type()
                for i in range(ROWS):
                    for j in range(COLUMNS):
                        c_board[i][j] = board[i][j]

                for i in range(3):
                    c_annotation[i] = annotation[i]

            if not c:
                util, strategy = cfr(board, annotation, 1, 1, 0, max_depth,
                                     blue_infostate=blue_infostate,
                                     blue_infostate_annotation=blue_infostate_annotation,
                                     red_infostate=red_infostate,
                                     red_infostate_annotation=red_infostate_annotation,
                                     policy_table=policy_table,
                                     utility_table=utility_table,
                                     utility_model=utility_model,
                                     policy_model=policy_model,
                                     turn_number=t)
            elif c:
                result = cfr(c_board, c_annotation, 1, 1, 0, max_depth)
                util = result.node_util
                c_strategy = result.strategy
                strategy = [c_strategy[i] for i in range(len(moves))]
                # Remove strategy array from memory
                free(result.strategy)

            print("Strategy: ")
            # for i, s in enumerate(strategy):
            #     print(f"{round(s*100)}%", end=' ')
            # print()
            print(strategy)
            # print(f"Strategy Sum: {sum(strategy):.2f}")

            print(f"Utility: {util:.2f}")

            # Set negative weights to zero to avoid errors
            for a, action in enumerate(strategy):
                if action < 0:
                    strategy[a] = 0

            # Only consider the top three moves
            sorted_strategy = sorted(strategy, reverse=True) # descending order
            # Get a list of the top three values
            top_three = sorted_strategy[:3]
            # Set all values below top three to zero (removes too suboptimal moves)
            for a, action in enumerate(strategy):
                if action not in top_three:
                    strategy[a] = 0
            # Renormalize the sanitized strategy
            strategy_sum = sum(strategy)
            for a, action in enumerate(strategy):
                strategy[a] = strategy[a]/strategy_sum
            print("Sanitized Strategy: ")
            # for i, s in enumerate(strategy):
            #     print(f"{round(s*100)}%", end=' ')
            # print()
            print(strategy)
            # Print the remaining moves in sanitized strategy
            print("Remaining Moves:")
            for i, action in enumerate(moves):
                if strategy[i] > 0:
                    print(f"{action}", end=" ")
                else:
                    print("XXXX", end=" ")
            print()

            move = random.choices(moves, weights=strategy, k=1)[0]

        print(f"Chosen Move: {move}")

        # Handle the saving of game moves
        if save_game:
            move_history.append(move)

        new_board, new_annotation = transition(board, annotation, move)
        # Examine move result (WIN, LOSS, TIE)
        result = get_result(board, annotation, move, new_board, new_annotation)

        # Update infostates
        blue_infostate, blue_infostate_annotation = private_observation(
            blue_infostate, blue_infostate_annotation, move, result)
        red_infostate, red_infostate_annotation = private_observation(
            red_infostate, red_infostate_annotation, move, result
        )

        # Update PBS
        # pbs, pbs_annotation = public_observation(pbs, pbs_annotation, move, result)

        # Overwrite old state
        board, annotation = new_board, new_annotation

        t += 1

    outcomes = ["DRAW", "BLUE", "RED"]
    print(f"Winner: {outcomes[reward(board, annotation)]}")

    # Handle saving of latest game to a JSON file
    if save_game:
        game_data.append(move_history)
        os.makedirs('history', exist_ok=True)
        with open('history/latest_game.json', 'w') as file:
            json.dump(game_data, file)
    print(f"Average branching: {round(moves_N/t)}")

    return policy_table, utility_table, t

class CFRResult(ctypes.Structure): 
    _fields_ = [("node_util", ctypes.c_double), 
                ("strategy", ctypes.POINTER(ctypes.c_double))]

def main():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # Sample random formation
    blue_formation = list(get_random_permutation(FORMATION_COMPONENTS))
    red_formation = list(get_random_permutation(FORMATION_COMPONENTS))

    faster = ctypes.CDLL('./cfr.so')

    # Ctypes array for annotation
    annotation = (ctypes.c_int * 3)
    # Convert the 2D list to a ctypes array 
    board = (ctypes.c_int * COLUMNS) * ROWS
    
    # Define the argument and return types of the C function 
    faster.cfr.argtypes = [board, annotation, c_double, c_double, c_int, c_int] 
    faster.cfr.restype = CFRResult

    # simulate_game(blue_formation, red_formation, cfr=faster.cfr, c=True)

    policy_table, utility_table, turns_taken = simulate_game(blue_formation, red_formation, cfr=cfr_train)

    # print(len(policy_table))
    # print(len(utility_table))

    rows = 0

    print("Writing to utility.csv...")
    # Write utility table contents to utility.csv
    with open('utility.csv', mode='w', newline='') as file:
        writer = csv.writer(file)
        # Write the header
        writer.writerow(['Infostate', 'Utility'])
        # Write the data
        for key, value in utility_table.items():
            writer.writerow([key, value])
            rows += 1

    print(f"Utility data ({rows} rows) successfully written to utility.csv")

    rows = 0

    print("Writing to policy.csv...")
    # Write policy table contents to policy.csv
    with open('policy.csv', mode='w', newline='') as file:
        writer = csv.writer(file)
        # Write the header
        writer.writerow(['InfostateAction', 'Probability'])
        # Write the data
        for key, value in policy_table.items():
            # Iterate through the actions in the infostate
            for i in range(len(value[0])): # Size of policy vector
                infostate_and_action = ""
                infostate_and_action += key # Infostate representation
                for j in range(4): # Length of an action representation
                    infostate_and_action += " " + value[1][i][j] # Concatenate infostate and action representation
                writer.writerow([infostate_and_action, value[0][i]])
                rows += 1

    print(f"Policy data ({rows} rows) successfully written to policy.csv")


    # simulate_game(blue_formation, red_formation)

if __name__ == "__main__":
    main()
