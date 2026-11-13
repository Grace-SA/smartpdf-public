import pytest
from smartppt.acceptance import edit_counts,rates,evaluate_page,summarize_documents,wilson


def region(text,box=(0,0,100,20),name='a'):return {'id':name,'text':text,'bbox':list(box)}


def test_exact_edits_and_unbounded_error_rate():
    assert edit_counts('cat','cut')=={'reference_characters':3,'predicted_characters':3,'substitutions':1,'deletions':0,'insertions':0,'correct_characters':2}
    assert rates(edit_counts('a','aaaaaaaa'))['character_error_rate']==7
    assert rates(edit_counts('','extra'))['character_accuracy'] is None


def test_image_fallback_is_missing_text():
    p=evaluate_page([region('Invoice 123.45')],[],truth_verified=True)
    assert p['character_recall']==0 and p['character_error_rate']==1 and not p['editable_success']
    assert p['character_precision'] is None


def test_swapped_numbers_are_not_matched_back_to_answers():
    truth=[region('North 123.45',name='north'),region('South 678.90',(0,40,100,60),'south')]
    predicted=[region('North 678.90'),region('South 123.45',(0,40,100,60))]
    p=evaluate_page(truth,predicted,truth_verified=True)
    assert p['numeric_regions_exact']==0 and p['character_error_rate']>0 and not p['editable_success']


def test_duplicates_and_wrong_location_are_failures():
    truth=[region('Amount 123.45')];p=evaluate_page(truth,truth+truth,truth_verified=True)
    assert p['insertions']>0 and not p['editable_success']
    wrong=evaluate_page(truth,[region('Amount 123.45',(300,0,400,20))],truth_verified=True)
    assert wrong['deletions']>0 and wrong['unmatched_prediction_characters']>0


def test_missing_truth_is_unmeasured():
    assert evaluate_page([region('Perfect')],[region('Perfect')])=={'measured':False,'reason':'independent_ground_truth_missing','editable_success':None}


def test_case_punctuation_and_digits_count():
    assert edit_counts('ABC: １２３.４５','ABC:123.45')['substitutions']==0
    assert edit_counts('ABC:123.45','abc12345')['substitutions']>0


def test_file_success_is_not_verified_editable_success():
    page=evaluate_page([region('Exact 123.45')],[region('Exact 123.45')],truth_verified=True);assert page['editable_success']
    docs=[{'eligible':True,'generated':True,'pages':[page]},{'eligible':True,'generated':True,'pages':[{'measured':False}]},{'eligible':False,'generated':False}]
    result=summarize_documents(docs)
    assert result['file_generation_rate']==1 and result['verified_editable_success_documents']==0
    assert result['truth_missing_documents']==1 and result['success_wilson_95'] is None
    docs[0].update(structure_verified=True,render_verified=True)
    assert summarize_documents(docs)['verified_editable_success_rate'] is None
    assert summarize_documents(docs)['verified_success_lower_bound']==.5


def test_intervals_and_empty_denominators():
    assert wilson(0,0) is None
    low,high=wilson(200,200);assert .98<low<1 and high==pytest.approx(1)
    assert summarize_documents([])['file_generation_rate'] is None


def test_correct_text_does_not_hide_geometry_errors():
    p=evaluate_page([region('Exact')],[region('Exact',(3,0,103,20))],truth_verified=True)
    assert p['character_error_rate']==0 and not p['editable_success']


def test_negative_sign_and_unknown_structure_are_not_success():
    from smartppt.acceptance import numbers
    assert numbers('Total: −123.45')!=numbers('Total: 123.45')
    p=evaluate_page([region('Exact')],[region('Exact')],truth_verified=True)
    result=summarize_documents([{'eligible':True,'generated':True,'pages':[p]}])
    assert result['verified_editable_success_rate'] is None and not result['success_rate_is_complete']


def test_invalid_truth_and_tolerance():
    for tolerance in (-1,float('nan'),float('inf')):
        with pytest.raises(ValueError):evaluate_page([region('A')],[],truth_verified=True,position_tolerance=tolerance)
    with pytest.raises(ValueError):evaluate_page([region('A'),region('B')],[],truth_verified=True)


def test_verified_blank_page_is_neutral_and_large_regions_are_bounded():
    p=evaluate_page([],[],truth_verified=True)
    assert p['editable_success'] and p['character_accuracy'] is None
    assert not evaluate_page([],[region('Unexpected')],truth_verified=True)['editable_success']
    with pytest.raises(ValueError):edit_counts('a'*6000,'b'*6000)
    assert edit_counts('a'*6000,'a'*6000)['correct_characters']==6000


def test_reading_order_only_orders_predictions_inside_their_geometry():
    a=region('A',(0,0,10,10));b=region('B',(0,20,10,30));a['reading_order']=1;b['reading_order']=0
    p=evaluate_page([region('BA',(0,0,10,30))],[a,b],truth_verified=True)
    assert p['character_error_rate']==0
    a['reading_order']=0
    with pytest.raises(ValueError):evaluate_page([region('BA')],[a,b],truth_verified=True)


def test_character_predictions_preserve_unicode_composition():
    predictions=[dict(region(char,(i*10,0,i*10+9,10)),reading_order=i) for i,char in enumerate('cafe\u0301')]
    result=evaluate_page([region('café')],predictions,truth_verified=True)
    assert result['character_error_rate']==0 and result['reference_characters']==4



@pytest.mark.parametrize('expected,actual', [('rate .5','rate 5'),('rate -.5','rate -5'),('values 1 2','values 12'),('values 12 3','values 1 23'),('rate 5 %','rate 5'),('amount (12.50)','amount 12.50'),('amount ($12.50)','amount $12.50')])
def test_numeric_changes_cannot_hide_below_character_tolerance(expected,actual):
    prefix='X'*2500+' '
    p=evaluate_page([region(prefix+expected)],[region(prefix+actual)],truth_verified=True)
    assert p['character_error_rate']<=.001
    assert p['numeric_regions_exact']==0 and not p['editable_success']


def test_numeric_date_boundaries_are_consistent_with_conversion_gate():
    from smartppt.acceptance import numbers
    assert numbers('January 1,1990')==numbers('January 1, 1990')==['1','1990']
    assert numbers('−.25%, １２３．４５')==['-.25%','123.45']
    assert numbers('2 1')!=numbers('1 2')
