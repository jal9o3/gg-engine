import logging, random

logging.basicConfig(level=logging.WARNING)

# GLobal constants
from world_constants import *

INFOROWS = 42 # 21 pieces per player
INFOCOLS = 21 # see designations below

# Define information state columns
PLAYER = 0 # to which player a piece belongs
# 1 - 15 is the probability of being pieces 1 - 15
ROW = 16
COLUMN = 17 # Current location of the piece (if captured, location of capturer)
RANGE_BOT = 18 # Lowest possible value of a piece
RANGE_TOP = 19 # Highest possible value of a piece, these are equal once identified
CAPTURED = 20 # Whether the piece has been captured

# Annotation indices
# CURRENT_PLAYER = 0, like in the world state annotation
WAITING_FLAG = 1 # Corresponds to WAITING_BLUE or WAITING_RED flags in world
POV_PLAYER = 2 # to which the infostate belongs

PIECES = [1, 2, 2, 2, 2, 2, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 15]
# The number of unique permutations of the above pieces
# VALUE_PERMUTATIONS_N = (math.factorial(21))/math.factorial(6)*math.factorial(2)

# SAMPLE_N = ((1.96**2)*0.5*(1 - 0.5))/0.05**2
# Representative sample size
# ADJUSTED_SAMPLE_N = SAMPLE_N/(1 + ((SAMPLE_N - 1)/VALUE_PERMUTATIONS_N))

# Sample n permutations from the set of unique value permutations
def value_permutation_sample(pieces, n):
    def get_random_permutation(pieces):
        permuted_list = pieces[:]
        random.shuffle(permuted_list)
        return tuple(permuted_list)
    
    seen = set()
    for i in range(n):
        permutation = get_random_permutation(pieces)
        while permutation in seen:
            permutation = get_random_permutation(pieces)
        seen.add(permutation)
    
    return seen

# Define the usage of bayes theorem
def bayes_theorem(hypothesis, evidence):
    # p(H|E) =
    # p(E|H)*p(H)/p(E)
    """
    Hypothesis takes the form [i, r] where i is the index of the piece under
    assessment, and r is the rank in question. Evidence is defined as an array
    of size INITIAL_ARMY (21), of which each element j has the form [f, c],
    where f is the lowest possible value for the piece j, and c is the highest
    possible value.
    """

    piece_to_assess, possible_value = hypothesis[0], hypothesis[1]
    sample_size = 1000

    # Estimate p(E|H)
    p_evidence = 0
    p_evidence_with_hypothesis = 0
    while p_evidence == 0: # avoid division by zero errors
        # Sample unique permutations
        sample = value_permutation_sample(PIECES, sample_size)
        for permutation in sample:
            # Estimate p(E)
            # Check if the current permutation matches the evidence
            is_match = True
            for piece, fact in enumerate(evidence):
                lower_bound, upper_bound = fact[0], fact[1]
                if lower_bound <= permutation[piece] <= upper_bound:
                    pass # Do nothing as long as the evidence is matched
                else:
                    is_match = False
                    break # Stop iterating over evidence once contradicted
            if is_match:
                p_evidence += 1 # Increase the probability of the evidence
                # Estimate p(E intersection H)
                # If the hypothesis is also true, increase p(E intersection H)
                if permutation[piece_to_assess] == possible_value:
                    p_evidence_with_hypothesis += 1
        
        # Scale probabilities in relation to the sample size
        p_evidence /= sample_size
        p_evidence_with_hypothesis /= sample_size

        # Obtain probability of hypothesis
        p_hypothesis = 0
        for piece in PIECES:
            if piece == possible_value:
                p_hypothesis += 1
        
        p_hypothesis /= sample_size

    # Recall: p(E|H) = p(E intersection H) / p(H)
    return p_evidence_with_hypothesis/p_evidence

def private_observation(infostate, infostate_annotation, action, result, update_probabilities=False):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    start_row, start_col, end_row, end_col = map(int, action)

    # Determine which piece to update range (attacker or defender)
    for i, piece in enumerate(infostate):
        if ((piece[ROW] == int(start_row) and piece[COLUMN] == int(start_col) 
            or piece[ROW] == int(end_row) and piece[COLUMN] == int(end_col))
            and piece[CAPTURED] == 0
            ):
            if i < INITIAL_ARMY:
                piece_to_update = i # current piece
            # Get the identified piece
            elif i >= INITIAL_ARMY:
                # Get the value of the identified piece
                for j, value in enumerate(piece):
                    if 1 <= j <= 15 and value == 1:
                        identified_value = j

    # Update the range of the piece based on the action result
    # Distinguish whether piece to update is the attacker or defender
    if (result != OCCUPY
        and infostate[piece_to_update][ROW] == start_row 
        and infostate[piece_to_update][COLUMN] == start_col):
        is_attacker = True
    else:
        is_attacker = False

    if result == DRAW:
        # Perform the update
        infostate[piece_to_update][RANGE_BOT] = identified_value
        infostate[piece_to_update][RANGE_TOP] = identified_value
    elif result == WIN:
        # Update as attacker or defender
        if is_attacker: # Unidentified is greater than the known piece
            if identified_value + 1 <= SPY:
                infostate[piece_to_update][RANGE_BOT] = identified_value + 1
            else: # Edge case for when private beats spy
                infostate[piece_to_update][RANGE_BOT] = PRIVATE
                infostate[piece_to_update][RANGE_TOP] = PRIVATE
        else: # Unidentified is less than the known piece
            if identified_value != PRIVATE:
                infostate[piece_to_update][RANGE_TOP] = identified_value - 1
            else:
                infostate[piece_to_update][RANGE_TOP] = SPY
                infostate[piece_to_update][RANGE_BOT] = SPY
    # No necessary update for occupation
    elif result == LOSS:
        if is_attacker:
            if identified_value != PRIVATE:
                infostate[piece_to_update][RANGE_TOP] = identified_value - 1
            else:
                infostate[piece_to_update][RANGE_BOT] = SPY
                infostate[piece_to_update][RANGE_TOP] = SPY
        else:
            if identified_value + 1 <= SPY:
                infostate[piece_to_update][RANGE_BOT] = identified_value + 1
            else:
                infostate[piece_to_update][RANGE_BOT] = PRIVATE
                infostate[piece_to_update][RANGE_TOP] = PRIVATE

    def handle_draw_update(piece):
        if piece[PLAYER] == BLUE:
            piece[ROW] = -1
            piece[COLUMN] = -1 # Send piece outside the board
        else:
            piece[ROW] = ROWS + 1
            piece[COLUMN] = COLUMNS + 1
        piece[CAPTURED] = 1

    for i, piece in enumerate(infostate):
        if (piece[ROW] == int(start_row) 
            and piece[COLUMN] == int(start_col)):
            # Draw
            if result == DRAW:
                handle_draw_update(piece)
            # Successful attacker or occupant or loss
            # Denotes either relocation or location of successful defender
            elif result == WIN or result == OCCUPY or result == LOSS:
                piece[ROW] = int(end_row)
                piece[COLUMN] = int(end_col)
                if result == LOSS and piece[PLAYER] == infostate_annotation[CURRENT_PLAYER]:
                    piece[CAPTURED] = 1

    for i, piece in enumerate(infostate):
        if (piece[ROW] == int(end_row)
            and piece[COLUMN] == int(end_col)):
            if result == DRAW:
                handle_draw_update(piece)
            elif result == WIN and piece[PLAYER] != infostate_annotation[CURRENT_PLAYER]:
                piece[CAPTURED] = 1
            # No defender in occupation
            # No location update for winning defender


    # Update the probabilities of piece identities
    if result != OCCUPY and update_probabilities:
        # Accumulate all gathered relevant evidence
        evidence = []
        for i, piece in enumerate(infostate):
            if i == INITIAL_ARMY:
                break
            evidence.append([piece[RANGE_BOT], piece[RANGE_TOP]])

        # Use conditional probability to calculate the likelihoods
        for i, piece in enumerate(infostate):
            if i == INITIAL_ARMY:
                break
            for j, value in enumerate(piece):
                if 1 <= j <= 15:
                    hypothesis = [i, j]
                    piece[j] = bayes_theorem(hypothesis, evidence)

    infostate_annotation[CURRENT_PLAYER] = RED if infostate_annotation[CURRENT_PLAYER] == BLUE else BLUE 

    return infostate, infostate_annotation
            
def print_infostate(infostate, annotation, show_probabilities=False):
    
    # For side by side display of top and bottom half of infostate
    split_infostate = [
        infostate[:INITIAL_ARMY], 
        infostate[INITIAL_ARMY:2*INITIAL_ARMY]
        ]
    
    def print_row_half(half_index, i, j):
        if show_probabilities:
            if abs(split_infostate[half_index][i][j]*100) < 100:
                print(f"{round(split_infostate[half_index][i][j]*100):2}", end=' ')
            else:
                print(f"{round(split_infostate[half_index][i][j]):2}", end=' ')
        else:
            if j < 1 or j > 15:
                print(f"{round(split_infostate[half_index][i][j]):2}", end=' ')

    print("\nInfostate: Opponent Pieces - Allied Pieces")
    if show_probabilities:
        print("Columns: Player-p(1:15)-x-y-floor-ceiling-is_captured")
    else:
        print("Columns: Player-x-y-floor-ceiling-is_captured")

    for i in range(INITIAL_ARMY):
        for j in range(INFOCOLS):
            # TODO: print row of first half
            print_row_half(0, i, j)
        print("  ", end='')
        for j in range(INFOCOLS):
            # TODO: print row of second half
            print_row_half(1, i, j)
        # print piece numbers
        print(f"   {i}+{i+INITIAL_ARMY}", end=" ")
        print()

def main():
    
    # seen = value_permutation_sample(PIECES, sample_size)
    # for permutation in seen:
    #     print(permutation)
    pass
                               

if __name__ == "__main__":
    main()