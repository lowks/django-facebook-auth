import urllib
from urlparse import parse_qs

from django.conf import settings
import facepy

from facebook_auth import models
from facebook_auth import utils


def _truncate(word, length, to_zero=False):
    if to_zero and len(word) > length:
        return word[0:0] # preserve type
    else:
        return word[:length]


class UserFactory(object):
    graph_api_class = facepy.GraphAPI

    def __create_username(self, profile):
            return profile['id'] # TODO better username

    def _product_user(self, access_token, profile, token_expiration_date=None):
        user_id = int(profile['id'])
        username = self.__create_username(profile)
        user, created = models.FacebookUser.objects.get_or_create(user_id=user_id,
                                                                  username=username)
        if created:
            user.set_unusable_password()

        def copy_field(field, to_zero=False):
            if field in profile:
                length = user._meta.get_field_by_name(field)[0].max_length
                setattr(user, field, _truncate(profile[field], length, to_zero=to_zero))

        copy_field('email', True)
        copy_field('first_name')
        copy_field('last_name')
        if access_token is not None:
            if getattr(settings, 'REQUEST_LONG_LIVED_ACCESS_TOKEN', False):
                access_token = self.get_long_lived_access_token(access_token)
            user.access_token = access_token
        user.access_token_expiration_date = token_expiration_date
        user.save()
        self.create_profile_object(profile, user)
        return user

    def get_long_lived_access_token(self, access_token):
        url_base = 'https://graph.facebook.com/oauth/access_token?'
        args = {
            'client_id': settings.FACEBOOK_APP_ID,
            'client_secret': settings.FACEBOOK_APP_SECRET,
            'grant_type': 'fb_exchange_token',
            'fb_exchange_token': access_token,
        }
        data = urllib.urlopen(url_base + urllib.urlencode(args)).read()
        try:
            access_token = parse_qs(data)['access_token'][-1]
        except KeyError:
            pass
        return access_token

    def get_user(self, access_token, token_expiration_date=None):
        try:
            profile = utils.get_from_graph_api(self.graph_api_class(access_token), 'me')
        except facepy.FacepyError:
            return None
        return self._product_user(access_token, profile, token_expiration_date)

    def get_user_by_id(self, uid):
        profile = utils.get_from_graph_api(self.graph_api_class(), uid)
        return self._product_user(None, profile)

    def create_profile_object(self, profile, user):
        if 'facebook_profile' in settings.INSTALLED_APPS:
            from facebook_profile import models as profile_models
            from facebook_profile import parser as profile_parser
            parser = profile_parser.FacebookDataParser(profile, True, True)
            try:
                data = parser.run()
                profile = profile_models.FacebookUserProfile.objects.create_or_update(data)
                profile.user = user
                profile.save()
            except profile_parser.FacebookDataParserCriticalError:
                pass


USER_FACTORY = UserFactory()


class FacebookBackend(object):
    def authenticate(self, code=None, redirect_uri=None):
        url_base = 'https://graph.facebook.com/oauth/access_token?'
        args = {
            'client_id': settings.FACEBOOK_APP_ID,
            'client_secret': settings.FACEBOOK_APP_SECRET,
            'redirect_uri': redirect_uri,
            'code': code
        }
        data = urllib.urlopen(url_base + urllib.urlencode(args)).read()
        try:
            access_token = parse_qs(data)['access_token'][-1]
        except KeyError:
            return None
        user = USER_FACTORY.get_user(access_token)
        return user

    def get_user(self, user_id):
        try:
            return models.FacebookUser.objects.get(pk=user_id)
        except models.FacebookUser.DoesNotExist: #@UndefinedVariable
            return None


class FacebookJavascriptBackend(FacebookBackend):
    def authenticate(self, access_token, token_expiration_date=None):
        return USER_FACTORY.get_user(access_token, token_expiration_date)
