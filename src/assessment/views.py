import json
import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from eventlog.signals import affect_check_completed, comprehension_check_completed
from library.models import Book
from .models import ComprehensionCheck, ComprehensionCheckResponse, AffectiveCheck, AffectiveCheckResponse

logger = logging.getLogger(__name__)

class AffectCheckView(LoginRequiredMixin, View):
    @staticmethod
    def create_from_request(request, affect_check_data):
        clusive_user = request.clusive_user
        logger.debug("create with data: %s", affect_check_data)
        logger.debug("create with data_bookId: %s", affect_check_data.get("bookId"))
        book = Book.objects.get(id=affect_check_data.get("bookId"))            

        (acr, created) = AffectiveCheckResponse.objects.get_or_create(user=clusive_user, book=book)
        acr.annoyed_option_response = affect_check_data.get('affect-option-annoyed')
        acr.bored_option_response = affect_check_data.get('affect-option-bored')
        acr.calm_option_response = affect_check_data.get('affect-option-calm')
        acr.confused_option_response = affect_check_data.get('affect-option-confused')
        acr.curious_option_response = affect_check_data.get('affect-option-curious')
        acr.disappointed_option_response = affect_check_data.get('affect-option-disappointed')
        acr.frustrated_option_response = affect_check_data.get('affect-option-frustrated')
        acr.happy_option_response = affect_check_data.get('affect-option-happy')
        acr.interested_option_response = affect_check_data.get('affect-option-interested')
        acr.okay_option_response = affect_check_data.get('affect-option-okay')
        acr.sad_option_response = affect_check_data.get('affect-option-sad')
        acr.surprised_option_response = affect_check_data.get('affect-option-surprised')

        acr.save()

        page_event_id=affect_check_data.get("eventId")
        
        affect_check_completed.send(sender=AffectCheckView,
                                  request=request, event_id=page_event_id,
                                  affect_check_response_id=acr.id,                                  
                                  answer=acr.toAnswerString())
        
    def post(self, request):
        try:
            affect_check_data = json.loads(request.body)
            logger.info('Received a valid affect check response: %s' % affect_check_data)
        except json.JSONDecodeError:
            logger.warning('Received malformed affect check data: %s' % request.body)
            return JsonResponse(status=501, data={'message': 'Invalid JSON in request body'}) 

        AffectCheckView.create_from_request(request, affect_check_data)                

        return JsonResponse({"success": "1"})

    def get(self, request, book_id):
        user = request.clusive_user
        book = Book.objects.get(id=book_id)        
        acr = get_object_or_404(AffectiveCheckResponse, user=user, book=book)            
        response_value = {
            "affect-option-annoyed": acr.annoyed_option_response,
            "affect-option-bored": acr.bored_option_response,
            "affect-option-calm": acr.calm_option_response,
            "affect-option-confused": acr.confused_option_response,
            "affect-option-curious": acr.curious_option_response,
            "affect-option-disappointed": acr.disappointed_option_response,
            "affect-option-frustrated": acr.frustrated_option_response,
            "affect-option-happy": acr.happy_option_response,
            "affect-option-interested": acr.interested_option_response,
            "affect-option-okay": acr.okay_option_response,
            "affect-option-sad": acr.sad_option_response,
            "affect-option-surprised": acr.surprised_option_response,
        }
        return JsonResponse(response_value)        

class ComprehensionCheckView(LoginRequiredMixin, View):
    @staticmethod
    def create_from_request(request, comprehension_check_data):    
        clusive_user = request.clusive_user
        book = Book.objects.get(id=comprehension_check_data.get("bookId"))

        (ccr, created) = ComprehensionCheckResponse.objects.get_or_create(user=clusive_user, book=book)
        ccr.comprehension_scale_response = comprehension_check_data.get('scaleResponse')
        ccr.comprehension_free_response = comprehension_check_data.get('freeResponse')
        ccr.save()

        # Fire event creation signals
        page_event_id =comprehension_check_data.get("eventId")
        comprehension_check_completed.send(sender=ComprehensionCheckView,
                                request=request, event_id=page_event_id,
                                comprehension_check_response_id=ccr.id,
                                key=ComprehensionCheck.scale_response_key,
                                question=comprehension_check_data.get('scaleQuestion'),
                                answer=ccr.comprehension_scale_response)
                                
        comprehension_check_completed.send(sender=ComprehensionCheckView,
                                request=request, event_id=page_event_id,
                                comprehension_check_response_id=ccr.id,
                                key=ComprehensionCheck.free_response_key,
                                question=comprehension_check_data.get('freeQuestion'),
                                answer=ccr.comprehension_free_response)            

    def post(self, request):            
        try:
            comprehension_check_data = json.loads(request.body)            
            logger.info('Received a valid comprehension check response: %s' % comprehension_check_data)
        except json.JSONDecodeError:
            logger.warning('Received malformed comprehension check data: %s' % request.body)
            return JsonResponse(status=501, data={'message': 'Invalid JSON in request body'})

        ComprehensionCheckView.create_from_request(request, comprehension_check_data)
                
        return JsonResponse({"success": "1"})

    def get(self, request, book_id):
        user = request.clusive_user
        book = Book.objects.get(id=book_id)        
        ccr = get_object_or_404(ComprehensionCheckResponse, user=user, book=book)            
        response_value = {ComprehensionCheck.scale_response_key: ccr.comprehension_scale_response,
                       ComprehensionCheck.free_response_key: ccr.comprehension_free_response}
        return JsonResponse(response_value)