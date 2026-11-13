from smartppt.partial_consensus import partial_line_agreement as check

def test_one_wrong_line_does_not_discard_verified_neighbor():
 assert check(['Revenue was 123.45.','Costs were 67.80.'],'Revenue was 123.45. Costs were 67.90.')==[True,False]
 assert check(['本期总收入为123.45元。','年度费用67.80元。'],'本期总收入为123.45元。年度费用67.90元。')==[True,False]

def test_number_prefix_and_lost_sign_never_approve():
 assert check(['Revenue 123','Incorrect footer'],'Revenue 1234 Correct footer')==[False,False]
 assert check(['123 revenue','Incorrect footer'],'-123 revenue Correct footer')==[False,False]
 assert check(['Revenue 123','Incorrect footer'],'Revenue 123.45 Correct footer')==[False,False]
 assert check(['Revenue 123','Incorrect footer'],'Revenue 123% Correct footer')==[False,False]

def test_duplicate_reordered_and_short_numbers_are_not_guessed():
 assert check(['Revenue 123.45','Revenue 123.45'],'Revenue 123.45 Revenue 123.45')==[False,False]
 assert check(['123.45','Bad footer'],'123.45 New footer')==[False,False]
 result=check(['North revenue 123.45','South revenue 678.90'],'South revenue 678.90 North revenue 123.45')
 assert result==[False,False]
 assert check(['Token revenue','Bad footer'],'Token revenues Good footer')==[False,False]


def test_added_verifier_words_on_line_boundaries_veto_erasure():
 assert check(["Revenue was 123.45", "Costs were 67.80"],"Net Revenue was 123.45 Costs were 67.80")==[False,True]
 assert check(["Revenue was 123.45", "Costs were 67.80"],"Revenue was 123.45 dollars Costs were 67.80")==[False,False]
def test_repeated_ineligible_block_does_not_enter_quadratic_alignment(monkeypatch):
 import smartppt.partial_consensus as module
 def forbidden(*args,**kwargs):raise AssertionError('No uniquely eligible line exists')
 monkeypatch.setattr(module,'SequenceMatcher',forbidden)
 lines=['repeated short line']*500
 assert module.partial_line_agreement(lines,' '.join(lines)+' mismatch')==[False]*500
