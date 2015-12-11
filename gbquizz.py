__module_name__ = 'gbquizz.py'
__module_version__ = '1.3.3'
__module_description__ = 'Quizz IRC'

import hexchat
import re
import random
import codecs
import unicodedata
import sys
import math

# Caractéristiques:
# Quizz: questions, scores, modificateurs #I, #N, ##, #R, #A, #M, #MR, #MO et combinaisons
# Multicast


BOLD = '\002'
COLORDEFAULT = '\00300,02'
COLORQUESTION = '\00302,00'
COLORSPECIAL = '\00308,02'
NICKMAXCHARS = 30

HELP_URL = 'http://suntorvic.free.fr/quizz/howto.html'

if not hexchat.get_pluginpref('gbquizz_ignored'):
	hexchat.set_pluginpref('gbquizz_ignored', 'LE LA LES DE DU DANS L\' THE A UN UNE DES')

def removeAccentChar(s, i):
	if s[i] == 'œ' or s[i] == 'Œ':
		return ['o', 'e']
	elif s[i] == 'æ' or s[i] == 'Æ':
		return ['a', 'e']
	elif s[i] == 'ō' or s[i] == 'Ō':
		return ['o', 'u']
	elif s[i] == 'ī' or s[i] == '':
		return ['i', 'i']
	elif s[i] == 'ū' or s[i] == 'Ū':
		return ['u', 'u']
	elif s[i] == 'ā' or s[i] == 'Ā':
		return ['a', 'a']
	elif s[i] == 'ß':
		return ['s', 's']
	else:
		return list(unicodedata.normalize('NFD', s[i])[0])
	
def removeAccents(s):
	result = []
	for i in range(0,len(s)):
		result = result + removeAccentChar(s, i)
	return u''.join(result)

class Setting:
	def __init__(self, pluginpref, defaultvalue, command, commandhelp = ''):
		self.pluginpref = pluginpref
		hexchat.hook_command(command, self.command, help=commandhelp)
		self.value = None
		if pluginpref:
			self.value = hexchat.get_pluginpref(pluginpref)
		if not self.value:
			self.value = defaultvalue
	def command(self, word, word_eol, userdata):
		if (len(word)>1):
			newValue = word_eol[1]
			self.value = newValue
			if self.pluginpref:
				hexchat.set_pluginpref(self.pluginpref, newValue)
		hexchat.prnt( word[0].upper() + ': ' + str(self.value))
		return hexchat.EAT_ALL
	def setvalue(self, new):
		if new:
			self.value = new
		if self.pluginpref:
			hexchat.set_pluginpref(self.pluginpref, self.value)
	def str(self):
		return str(self.value)
	def int(self):
		return int(self.value)
	def __del__(self):
		hexchat.unhook(self.command)

class Question:
	def __init__(self, type, enunciated, answers):
		self.type = type
		self.enunciated = enunciated
		self.answers = answers
		self.cooldown = 0 # or Bot's int(self.tick.value) ?

class Player:
	def __init__(self, name, score = 0, beststreak = 0):
		self.name = name or ''
		self.score = score or 0
		self.beststreak = beststreak or 0
	def streaking(self, value):
		if value > self.beststreak:
			self.beststreak = value

class Bot:
	def __init__(self):
		self.givenAnswers = []
		self.questions = []
		self.quizzfile = Setting('gbquizz_quizzfile', '', 'QUIZZFILE', '/QUIZZFILE <nom du fichier>: régler le nom du fichier de quizz. Sans argument, permet de connaître ce nom de fichier.')
		self.timeHint = Setting('gbquizz_timehint', 15, 'QUIZZTIMEHINT', '/QUIZZTIMEHINT <temps en secondes>: temps restant à l\'affichage de l\'indice.')
		self.timeQuestion = Setting('gbquizz_timequestion', 60, 'QUIZZTIMEQUESTION', '/QUIZZTIMEQUESTION <temps en secondes>: durée de chaque question.')
		self.multicastEnabled = Setting('gbquizz_multicastenabled', 0, 'QUIZZMULTICAST', '/QUIZZMULTICAST <1 ou 0>: activer ou désactiver le multicast.')
		self.timePause = Setting('gbquizz_timepause', 15, 'QUIZZTIMEPAUSE', '/QUIZZTIMEPAUSE <temps en secondes>: durée de chaque pause.')
		self.channel = Setting(None, hexchat.get_info('channel'), 'QUIZZCHANNEL', '/QUIZZCHANNEL <canal>: changer le canal du bot de quizz.')
		self.tick = Setting('gbquizz_tick', 0, 'QUIZZTICK', '/QUIZZTICK <valeur>: changer la valeur du temps pour le bot.')
		self.mode = 0
		self.ignoredList = hexchat.get_pluginpref('gbquizz_ignored').split(' ')
		self.loadScores()
		self.currentAnswers = []
		hexchat.hook_command('QUIZZSTART', self.startQuizz)
		hexchat.hook_command('QUIZZSTOP', self.stop)
		hexchat.hook_command('QUESTION', self.newQuestion)
		hexchat.hook_server('PRIVMSG', self.messageHook)
		hexchat.hook_server('JOIN', self.joinHook)
		hexchat.hook_unload(self.quit)
		
	#def __del__(self):
		#hexchat.unhook(self.messageHook)
		#hexchat.unhook(self.timerHook)
		#hexchat.unhook(self.joinHook)
		
	def joinHook(self, word, word_eol, userdata):
		nick = word[0][1:].split('!')[0]
		if hexchat.nickcmp(nick, hexchat.get_info("nick")) == 0:
			self.SendMessage(BOLD + COLORDEFAULT + 'Chargement du quizzbot ' + COLORSPECIAL + __module_name__ + COLORDEFAULT + ' version ' + COLORSPECIAL + __module_version__ + COLORDEFAULT + ' ! Envoyez ' + COLORSPECIAL + '!quizz' + COLORDEFAULT + ' pour lancer le jeu. ' + COLORSPECIAL + '!quizzhelp' + COLORDEFAULT + ' pour connaître les commandes. ' + COLORSPECIAL + HELP_URL + COLORDEFAULT + ' pour l\'aide en ligne.', word[2][1:])
		return hexchat.EAT_NONE

	def quit(self, userdata):
		self.writeScores()
		self.SendMessage(BOLD + COLORDEFAULT + 'Quizzbot déchargé.')

	def loadScores(self):
		self.players = []
		name = ''
		i=0
		while True:
			name = hexchat.get_pluginpref('gbquizz_player' + str(i) + '_name')
			score = hexchat.get_pluginpref('gbquizz_player' + str(i) + '_score')
			beststreak = hexchat.get_pluginpref('gbquizz_player' + str(i) + '_beststreak')
			i = i+1
			if name != None and score != None:
				self.players.append(Player(name, score, beststreak))
			else:
				break

	def writeScores(self):
		i = 0
		for player in self.players:
			hexchat.set_pluginpref('gbquizz_player' + str(i) + '_name', player.name)
			hexchat.set_pluginpref('gbquizz_player' + str(i) + '_score', player.score)
			hexchat.set_pluginpref('gbquizz_player' + str(i) + '_beststreak', player.beststreak)
			i = i + 1

	def loadQuizz(self):
		return self.loadQFile() and self.loadCooldownFile('cooldowns')

	def SendMessage(self, message, channel = None):
		if not channel:
			channel = self.channel.str()
		hexchat.command('MSG ' + channel + ' ' + message)

	def stripPhrase(self, phrase, **args):
		if (not 'keepAccents' in args or not args['keepAccents']):
			stripped = removeAccents(phrase.strip()).lower()
		else:
			stripped = phrase.strip().lower()
		for uselessWord in self.ignoredList:
			if stripped.startswith(uselessWord.lower()) and len(stripped) > (len(uselessWord)) and uselessWord[-1]=="'" :
				stripped = stripped[len(uselessWord):].strip()
				break
			if stripped.startswith(uselessWord.lower() + ' ') and len(stripped) > (len(uselessWord)+1):
				stripped = stripped[len(uselessWord):].strip()
				break
		noPunctuation = stripped.replace('.','')
		noPunctuation = noPunctuation.replace(',','')
		noPunctuation = noPunctuation.replace('!','')
		noPunctuation = noPunctuation.replace('?','')
		noPunctuation = noPunctuation.strip()
		if len(noPunctuation) > 3:
			stripped = noPunctuation
		if len(stripped) > 0:
			#if stripped[-1] in ['.','!','?']:
				#stripped = stripped[:-1]
			return stripped
		return phrase.strip().lower()

	def loadQFile(self):
		self.questions = []
		try:
			questionfile = codecs.open(self.quizzfile.str(), 'r', 'utf-8')
			qmatch = re.compile('((?:#[A-Z#]+)?)(.*?)\\\\(.+)$')
			for line in questionfile:
				result = qmatch.match(line)
				if result:
					type = result.group(1)[1:]
					enunciated = result.group(2)
					if type=='S':
						answers = [result.group(3)]
					else:
						answers = result.group(3).split('\\')					# Last character is a line ending
					self.questions.append(Question(type,enunciated,answers))
			questionfile.close()
			hexchat.prnt('Fichier ' + questionfile.name + ' lu. ' + str(len(self.questions)) + ' questions chargées !')
			return True
		except Exception as e:
			hexchat.prnt('Le fichier \'' + self.quizzfile.str() + '\' n\'a pas pu être ouvert en lecture.' + str(e))
			if questionfile:
				questionfile.close()
			return False

	def loadCooldownFile(self, filename):
		cdfile = open(hexchat.get_info('configdir') + '/' + filename, 'r')
		if cdfile:
			i = 0
			for cdline in cdfile:
				if i < len(self.questions):
					self.questions[i].cooldown = int(cdline)
					i = i + 1
			cdfile.close()
			return True
		return False

	def writeCooldownFile(self, filename):
		cdfile = open(hexchat.get_info('configdir') + '/' + filename, 'w')
		if cdfile:
			for question in self.questions:
				cdfile.write(str(int(question.cooldown)) + '\n')
			cdfile.close()
			return True
		return False

	def startQuizz(self, word = None, word_eol = None, userdata = None):
		if self.loadQuizz():
			if userdata:
				self.channel.setvalue(str(userdata))
			if hexchat.get_info('channel')[0] == '#' and not self.channel.str()[0] == '#':
				self.channel.setvalue(hexchat.get_info('channel'))
			hexchat.prnt('Starting quizz on channel: ' + self.channel.str() + ' now on ' + hexchat.get_info('channel'))
			self.SendMessage(BOLD + COLORDEFAULT + 'Le quizz commence' + COLORDEFAULT + ' !')
			self.mode = 1
			self.timer = 0
			self.currentQuestion = None
			hexchat.hook_timer(1000, self.timerHook)
			self.currentStreak = 0
			self.lastWinner = None
			self.currentStreak = 0
			return hexchat.EAT_ALL

	def stop(self, word = [""], word_eol = [""], userdata = None):
		self.SendMessage(BOLD + COLORDEFAULT + 'Le jeu s\'arrête.')
		self.mode = 0
		try:
			hexchat.unhook(self.timerHook)
		except SystemError:
			hexchat.prnt('Unable to unhook the timer.')
		self.writeCooldownFile('cooldowns')
		self.writeScores()
		return hexchat.EAT_ALL

	def addToQuizz(self, question, nick, channel):
		try:
			qmatch = re.compile('((?:#[A-Z#]+)?)(.*?)\\\\(.+)$')
			if qmatch.match(question):
				questionfile = codecs.open(self.quizzfile.str(), 'a', 'utf-8')
				questionfile.write(question + '\n')
				questionfile.close()
				if channel == self.channel.str():
					self.SendMessage(BOLD + COLORDEFAULT + nick + ' a ajouté une question !')
				else:
					self.SendMessage(BOLD + COLORDEFAULT + 'La question a été ajoutée !', nick)
					self.SendMessage(BOLD + COLORDEFAULT + nick + ' a ajouté une question !')
				if self.mode > 0:
					self.writeCooldownFile('cooldowns')
					if self.currentQuestion:
						currentQuestionId = self.questions.index(self.currentQuestion)
					self.loadQuizz()
					if currentQuestionId:
						self.currentQuestion = self.questions[currentQuestionId]
				return True
		except Exception as e:
			hexchat.prnt(BOLD + 'Le fichier ' + self.quizzfile.str() + ' n\'a pas pu être ouvert en écriture.')
			if questionfile:
				questionfile.close()
			return False

	def messageHook(self, word, word_eol, userdata):
		if self.mode > 0 and word[2] == self.channel.str() and self.currentQuestion and self.checkAnswer(word_eol[3][1:], self.getNick(word[0])) and ( not (len(self.currentQuestion.type) > 0 and self.currentQuestion.type[0] == 'M' and self.currentAnswers)):
			self.endQuestion()
		elif  len(word)>4 and word[3] == ':!quizzadd':
			self.addToQuizz(word_eol[4], self.getNick(word[0]), word[2])
		elif len(word)>3 and self.mode == 0 and word[2][0]=='#' and word[3]==':!quizz':
			self.startQuizz(None, None, word[2])
		elif len(word)>3 and word[3]==':!quizzhelp':
			self.sendHelp(word[2])
		elif self.mode > 0 and word[2] == self.channel.str() and len(word)>3 and word[3]==':!stop':
			self.stop()
		elif len(word)>4 and word[3]==':!score':
			self.sendScore(word[4], word[2])
		elif len(word)>3 and word[3].startswith(':!top'):
			n = int(word_eol[3][5:])
			if n>0 and n<11:
				self.top(n, word[2])
		elif self.mode > 0 and word[2] == self.channel.str() and len(word)>3 and word[3]==':!tip':
			self.giveHint()
		elif self.mode > 0 and len(word)>3 and word[3]==':!question':
			self.sendQuestionText(word[2])
		return hexchat.EAT_NONE

	def timerHook(self, userdata):
		if self.mode > 0:
			self.tick.setvalue(int(self.tick.value)+1)
			if self.timer == 0:
				if self.currentQuestion:
					printedAnswers = ''
					if len(self.currentQuestion.type) > 0 and self.currentQuestion.type[0] == 'M':
						for answer in self.currentAnswers:
							 printedAnswers = printedAnswers + ('' if printedAnswers == '' else ', ') + answer.strip()
					else:
						printedAnswers = self.currentAnswers[0].strip()
					self.SendMessage(BOLD + COLORDEFAULT + 'La réponse était: ' + COLORSPECIAL + printedAnswers + COLORDEFAULT + ' !')
					if self.lastWinner:
						self.lastWinner = None
					self.endQuestion()
				else:
					self.newQuestion()
			else:
				if self.timer == self.timeHint.int() and self.currentQuestion:
					self.giveHint()
				self.timer = self.timer - 1
			return 1
		else:
			return 0

	def newQuestion(self, word = None, word_eol = None, userdata = None):
		self.givenAnswers = []
		if word:
			if self.mode == 0 or self.currentQuestion:
				return
			number = int(word[1])
			if 0 <= number < len(self.questions):
				self.currentQuestion = self.questions[number]
		if not self.currentQuestion:
			currentQuestionId = random.randint(0,len(self.questions)-1)
			cdvalue = 1.2 * min(self.questions, key=lambda question: question.cooldown).cooldown
			i = 0
			while self.questions[currentQuestionId].cooldown > cdvalue and i < len(self.questions):
				currentQuestionId = ( currentQuestionId + 1 ) % len(self.questions)
				i = i + 1
			self.currentQuestion = self.questions[currentQuestionId]
		self.currentAnswers = list(self.currentQuestion.answers)
		if self.currentQuestion.type == 'S':
			word = list(self.currentQuestion.answers[0].strip())
			random.shuffle(word)
			scrambledword = ''.join(word)
			self.questionText = BOLD + COLORSPECIAL + ((self.currentQuestion.enunciated.strip() + ' ') if self.currentQuestion.enunciated != '' else '') + COLORDEFAULT + 'Mot mélangé:' + COLORQUESTION + ' ' + scrambledword.upper()
		else:
			i = 0
			message_modifier = ''
			message_index = ''
			if len(self.currentQuestion.type) > i and self.currentQuestion.type[i] == 'M':
				i=i+1
				if len(self.currentQuestion.type) > i and self.currentQuestion.type[i] == 'R':
					self.currentAnswers = random.sample(self.currentAnswers, random.randint(1,len(self.currentAnswers)))
					i=i+1
				elif len(self.currentQuestion.type) > i and self.currentQuestion.type[i] == 'O':
					i=i+1
				message_modifier = COLORDEFAULT + ' x' + COLORSPECIAL + str(len(self.currentAnswers)) + ' ' + COLORDEFAULT
			elif len(self.currentQuestion.type) > i and self.currentQuestion.type[i] in ['R','N','#','I']:
				answerIndex = self.pickOneRandomAnswer()
			if len(self.currentQuestion.type) > i and self.currentQuestion.type[i] == 'N':
				for answer in range(0,len(self.currentAnswers)):
					if answerIndex:
						printIndex = str(answerIndex+1)
					else:
						printIndex = str(answer+1)
					message_index = message_index + ( '' if message_index == '' else ', ' ) + COLORDEFAULT + ' #' + COLORSPECIAL + printIndex
				i=i+1
			elif len(self.currentQuestion.type) > i and self.currentQuestion.type[i] == '#':
				for answer in range(0,len(self.currentAnswers)):
					if answerIndex:
						answerIndex = str(answerIndex+1)
					else:
						answerIndex = str(answer+1)
					message_index = message_index + ( '' if message_index == '' else ', ' ) + COLORDEFAULT + ' numéro: ' + COLORSPECIAL + self.currentAnswers[0].strip()
					self.currentAnswers[0] = answerIndex
				i=i+1
			if len(self.currentQuestion.type) > i and self.currentQuestion.type[i] == 'I':
				for answer in range(0,len(self.currentAnswers)):
					separation = self.currentAnswers[answer].split(':',1)
					if len(separation)>1:
						printIndex = separation[0]
						self.currentAnswers[answer] = separation[1]
					else:
						if answerIndex:
							printIndex = str(answerIndex)
						else:
							printIndex = str(answer)
					message_index = message_index + ( '' if message_index == '' else ', ' ) + printIndex.strip()
				i=i+1
			if len(self.currentQuestion.type) > i and self.currentQuestion.type[i] == 'A':
				message_qtype = 'Action'
			else:
				message_qtype = 'Question'
			self.questionText = BOLD + COLORSPECIAL + message_qtype + message_modifier + ':' + COLORQUESTION + ' ' + self.currentQuestion.enunciated.strip() + ' ' + message_index.strip()
		self.sendQuestionText()
		self.timer = self.timeQuestion.int()
		return hexchat.EAT_ALL

	def sendQuestionText(self, dest = None):
		if self.currentQuestion and self.questionText != '':
			self.SendMessage(self.questionText, dest)

	def endQuestion(self):
		self.timer = self.timePause.int()
		self.currentQuestion.cooldown = int(self.tick.value)
		self.currentQuestion = None
		self.SendMessage(BOLD + COLORDEFAULT + 'Prochaine question dans ' + self.timePause.str() + ' secondes...')
		self.currentAnswers = []
		self.questionText = ''

	def checkAnswer(self, message, nick):
		strippedMessage = ''
		if (len(self.currentQuestion.type) > 0 and self.currentQuestion.type[-1]=='A'):
			if (message.startswith('\001ACTION') and message[-1]=='\001'):
				strippedMesssage = self.stripPhrase(message[7:-1])
			else:
				return False
		else:
			strippedMesssage = self.stripPhrase(message)
		for answer in self.currentAnswers:
			if strippedMesssage == self.stripPhrase(answer):
				winner = self.getPlayer(nick)
				if winner:
					winner.score = winner.score + 1
				else:
					winner = Player(nick, 1, 0)
					self.players.append(winner)
				if self.lastWinner == winner:
					self.currentStreak = self.currentStreak + 1
					if self.currentStreak % 4 < 3:
						streakMessage = ' (' + str(self.currentStreak) + ' d\'affilées !)'
					else:
						textsStreak = [' (' + str(self.currentStreak) + ' d\'affilées ! INCROYABLE)',
							' (' + str(self.currentStreak) + ' d\'affilées ! COMBO)',
							' (' + str(self.currentStreak) + ' d\'affilées ! UNSTOPPABLE)',
							' (' + str(self.currentStreak) + ' d\'affilées ! M-M-MONSTER QUIZZ)',
							' (' + str(self.currentStreak) + ' d\'affilées ! OSCAR WILDE EN PERSONNE)',
							' (' + str(self.currentStreak) + ' d\'affilées ! GODLIKE)']
						streakMessage = textsStreak[random.randint(0,len(textsStreak))-1]
				else:
					if self.lastWinner and self.currentStreak > 3:
						textsStreak = ['! ' + self.lastWinner.name + ' EST SALÉ !',
							'! ' + self.lastWinner.name + ' S\'EST FAIT ROULER DESSUS !',
							'! C-C-C-COMBO BREAKER !',
							'! ' + winner.name + ' A DÉTRÔNÉ ' + self.lastWinner.name + ' !']
						streakMessage = textsStreak[random.randint(0,len(textsStreak)-1)]
					else:
						streakMessage = ''
					self.currentStreak = 1
					self.lastWinner = winner
				winner.streaking(self.currentStreak)
				self.SendMessage(BOLD + COLORDEFAULT + winner.name + ' a trouvé la réponse: ' + COLORSPECIAL + answer.strip() + COLORDEFAULT + ' (' + str(winner.score) + ' point'+ ( 's' if winner.score > 1 else '' ) + ')' + streakMessage + ' !')
				self.currentAnswers.remove(answer)
				if self.multicastEnabled.int() > 0:
					self.multicast()
				return True
			if self.currentQuestion.type.startswith('MO'):
				break
		# Si c'etait une mauvaise reponse on l'ajoute a la liste des reponses donnees
		self.givenAnswers.append({'name': nick, 'answer': message})
		return False

	def giveHint(self, **args):
		if self.currentQuestion:
			solution = self.stripPhrase(self.currentAnswers[0], keepAccents = True)
			try:
				intval = int(solution)
				closest = None
				for i in range(0,len(self.givenAnswers)-1):
					try:
						if (not closest) and int(self.givenAnswers[i]['answer']):
							closest = self.givenAnswers[i]
						elif closest and abs(int(self.givenAnswers[i]['answer'])-intval) <= abs(int(closest['answer'])-intval):
							closest = self.givenAnswers[i]
					except ValueError:
						next
				if closest and len(self.givenAnswers)>1:
					self.SendMessage(BOLD + COLORSPECIAL + closest['name'] + COLORDEFAULT + " EST LE PLUS PROCHE AVEC " + str(int(closest['answer'])))
			except ValueError:
				if len(solution)>3:
					position = random.randint(0,1)
					if position == 0:		# beginning
						hint = solution[0:max(2,int(len(solution)/7))] + '...'
					else:					# ending
						hint = '...' + solution[-max(2,int(len(solution)/7)):]
					self.SendMessage(BOLD + COLORDEFAULT + 'Indice:' + COLORSPECIAL + ' ' + hint)

	def getNick(self, address):
		nickend = address.index('!')
		nick = address[1:nickend]
		return nick

	def pickOneRandomAnswer(self):
		answerIndex = random.randint(0, len(self.currentAnswers) - 1)
		self.currentAnswers = [self.currentAnswers[answerIndex]]
		return answerIndex

	def getPlayer(self, nick):
		for player in self.players:
			if player.name.lower() == nick.lower():
				return player
		return None

	def top(self, nb, dest = None):
		i = 1
		self.players.sort(key=lambda player: player.score, reverse=True)
		for player in self.players[:nb]:
			self.SendMessage(BOLD + COLORSPECIAL + str(i) + COLORDEFAULT + '. ' + COLORSPECIAL + player.name + COLORDEFAULT + ': ' + str(player.score) + ' points, ' + str(player.beststreak) + ' d\'affilée max.', dest)
			i = i + 1

	def sendHelp(self, dest = None):
		self.SendMessage(BOLD + COLORDEFAULT + __module_name__ + ' version ' + __module_version__ + '. '+ COLORSPECIAL + '!quizz' + COLORDEFAULT + ' pour lancer le jeu, ' + COLORSPECIAL + '!stop' + COLORDEFAULT + ' pour l\'arrêter, ' + COLORSPECIAL + '!question' + COLORDEFAULT + ' pour répéter, ' + COLORSPECIAL + '!tip' + COLORDEFAULT + ' pour un indice, ' + COLORSPECIAL + '!top N' + COLORDEFAULT + ' pour le classsement des N meilleurs, ' + COLORSPECIAL + '!score PSEUDO' + COLORDEFAULT + ' pour connaître le score de PSEUDO.', dest)

	def sendScore(self, nick, dest = None):
		player = self.getPlayer(nick)
		if player:
			self.SendMessage(BOLD + COLORDEFAULT + player.name + ': ' + str(player.score) + ' points. Meilleure série: ' + str(player.beststreak) + ' réponses.', dest)

	def multicast(self):
		userlist = hexchat.get_list('users')
		nicklist = []
		if userlist:
			for u in userlist:
				nicklist.append(u.nick)
			i = 1
			while self.multicastEnabled.int() > 0 and random.randint(1,math.floor(2+8/(i*i)))==1 and i < 7:
				multicastReceiverNick = nicklist[random.randint(0,len(nicklist)-1)]
				multicastReceiver = self.getPlayer(multicastReceiverNick)
				if multicastReceiver:
					multicastReceiver.score = multicastReceiver.score + 1
				else:
					multicastReceiver = Player(multicastReceiverNick,1,0)
					self.players.append(multicastReceiver)
				self.SendMessage(BOLD + COLORSPECIAL + 'MULTICAST' + ( ( COLORDEFAULT + ' x' + COLORSPECIAL + str(i) ) if i > 1 else '' ) + COLORDEFAULT +' ! ' + COLORSPECIAL + multicastReceiver.name + COLORDEFAULT + ' gagne 1 point !')
				i = i + 1

gamebot = Bot()
