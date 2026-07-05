// js de la page index.cfm — logique 100% ancienne + rendu visuel nouvelle maquette
$(document).ready(function(){
	var  table=[];
	var  tableAvailable=[];
	var expression ;
	var messages = new Array();
	messages[1] = $("#msgpasAct").val(); 
	messages[2] = $("#errorsearch").val();

	/* ══ SVG & TYPES pour le rendu visuel ══ */
	var SVG = {
		produit : '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>',
		dest    : '<path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/>',
		lieu    : '<path d="M3 21h18M3 10h18M5 6l7-3 7 3M4 10v11M20 10v11M8 14v3M12 14v3M16 14v3"/>',
		theme   : '<circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/>',
		excur   : '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
		ticket  : '<path d="M2 9a3 3 0 010-6h20a3 3 0 010 6v6a3 3 0 010 6H2a3 3 0 010-6V9z"/><line x1="12" y1="3" x2="12" y2="9"/><line x1="12" y1="15" x2="12" y2="21"/>',
		transfer: '<rect x="1" y="3" width="15" height="13" rx="2"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>',
		pays    : '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 010 20M12 2a15.3 15.3 0 000 20"/>'
	};
	var TYPES = {
		1: { svg:'dest',    bg:'#eef4ff', stroke:'#2255cc', group:'Destinations'      },
		2: { svg:'excur',   bg:'#fff8f0', stroke:'#c06000', group:'Types de produits' },
		3: { svg:'lieu',    bg:'#f0faf5', stroke:'#0a7a50', group:'Lieux visites'     },
		4: { svg:'theme',   bg:'#f5f0ff', stroke:'#6633cc', group:'Themes'            },
		5: { svg:'pays',    bg:'#fff5f0', stroke:'#cc4400', group:'Pays'              }
	};
	var TYPE_PRODUIT = {
		'424': { svg:'excur',    bg:'#fff8f0', stroke:'#c06000', sub:'Visites guidees, circuits'     },
		'449': { svg:'ticket',   bg:'#eef4ff', stroke:'#2255cc', sub:'Entrees, coupe-file, pass'     },
		'429': { svg:'transfer', bg:'#f0faf5', stroke:'#0a7a50', sub:'Navettes, transferts aeroport' },
		'1'  : { svg:'excur',    bg:'#fff8f0', stroke:'#c06000', sub:'Visites guidees, circuits'     },
		'2'  : { svg:'ticket',   bg:'#eef4ff', stroke:'#2255cc', sub:'Entrees, coupe-file, pass'     },
		'3'  : { svg:'transfer', bg:'#f0faf5', stroke:'#0a7a50', sub:'Navettes, transferts aeroport' },
		'4'  : { svg:'excur',    bg:'#fff8f0', stroke:'#c06000', sub:'Visite guidee privee'          },
		'5'  : { svg:'excur',    bg:'#fff8f0', stroke:'#c06000', sub:'Circuit organise'              }
	};

	/* ── Highlight terme saisi ── */
	function hl(text, term) {
		if (!term || term.length < 2) return text;
		var esc = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
		return text.replace(new RegExp('(' + esc + ')', 'gi'), '<mark>$1</mark>');
	}

	/* ── Détermine icône/groupe à partir de table[idx] ── */
	function getVisual(idx) {
		var raw = table[idx] || '';
		var p   = raw.split('_');
		var lastSeg = (p[p.length-1]||'').toLowerCase().replace(/\s/g,'');
		var isProduit = (lastSeg === 'produit' || lastSeg === 'produitt');
		var so = isProduit ? 1 : (parseInt(p[p.length-1],10)||1);
		if (so < 1 || so > 5) so = 1;
		/* Fix : parser coupe sur virgule dans le nom → perd le _3 final
		   Si idLieu (p[6]) > 0, c'est forcément un lieu visité (so=3) */
		var idLieuCheck = (p[6]||'').trim();
		if (so === 1 && idLieuCheck && !isNaN(idLieuCheck) && parseInt(idLieuCheck) > 0) so = 3;
		var idType = p[2]||'0';
		var baseType = TYPES[so]||TYPES[1];
		var t, sub='';
		if (isProduit) {
			t = {svg:'produit',bg:'#fff0f2',stroke:'#D01F3C',group:'Produits'};
			sub = (p[p.length-2]||'').trim();
			sub = sub ? sub+' - Réf : '+p[2] : 'Réf : '+p[2];
		} else if (so===1) {
			t = baseType;
			/* Distinguer Pays et Ville depuis search.cfc :
			   Pays  : p[1]="0" (pas d'idVille), p[7]=idPays > 0
			   Ville : p[1]=idVille > 0 */
			var idVilleVal = (p[1]||'').trim();
			var idPaysVal  = (p[7]||'').trim();
			var estPays = (!idVilleVal || idVilleVal==='0' || idVilleVal===p[0].trim())
			              && idPaysVal && !isNaN(idPaysVal) && idPaysVal!=='0';
			if (estPays) {
				sub = 'Pays';
			} else {
				sub = 'Ville';
			}
		} else if (so===2) {
			var tp = TYPE_PRODUIT[idType]||TYPE_PRODUIT['1'];
			t = {svg:tp.svg,bg:tp.bg,stroke:tp.stroke,group:baseType.group};
			sub = tp.sub||'Activite';
		} else {
			t = baseType;
			if (so===3) {
				/* p[9] contient souvent le so ("3") → ignorer si numérique
				   Fallback sur p[0].split(' - ')[0] pour la ville */
				var nv=(p[8]&&p[8].trim()&&isNaN(p[8].trim()))?p[8].trim():'';
				if(!nv){var lp=(p[0]||'').split(' - ');nv=lp.length>1?lp[0].trim():'';}
				sub=nv?nv+' - Monument':'Monument';
			} else if(so===4){sub='Thème';}
			else if(so===5){sub='Pays';}
		}
		return {so:so,t:t,sub:sub,isProduit:isProduit};
	}

	/* ── Panel dropdown ── */
	var $panel, $wrap;
	function initPanel(){
		$wrap=$('#deSearchWrapper');
		if(!$wrap.length) $wrap=$('#deSearchBar').parent();
		$('#de-dd').remove();
		$panel=$('<div id="de-dd"></div>').appendTo($wrap);
	}
	function openBar() { $('#deSearchBar').addClass('de-open'); if($panel)$panel.show(); }
	function closeBar(){ $('#deSearchBar').removeClass('de-open'); if($panel){ $panel.hide(); $panel.find('.de-keynav').removeClass('de-keynav'); $panel.removeAttr('data-keynav'); } }

	/* ── Rendu du panel custom ── */
	function renderPanel(tags, term){
		var html='', prevGroup=null;
		for(var i=0;i<tags.length;i++){
			var v=getVisual(i);
			var group=v.t.group;
			var nextGroup=(i<tags.length-1)?getVisual(i+1).t.group:null;
			var isLast=(i===tags.length-1)||(nextGroup!==group);
			if(group!==prevGroup){
				html+='<div class="de-sec"><span class="de-sec-lbl">'+group+'</span><span class="de-sec-line"></span></div>';
				prevGroup=group;
			}
			html+='<div class="de-item'+(isLast?' de-last':'')+'" data-idx="'+i+'" data-lbl="'+encodeURIComponent(tags[i])+'">'
				+'<div class="de-icon" style="background:'+v.t.bg+';">'
				+'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="'+v.t.stroke+'" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">'+SVG[v.t.svg]+'</svg></div>'
				+'<div class="de-body">'
				+'<div class="de-name">'+hl(tags[i],term)+'</div>'
				+(v.sub?'<div class="de-sub">'+v.sub+'</div>':'')
				+'</div></div>';
		}
		$panel.removeAttr('data-keynav').html(html);
		openBar();
		$panel.scrollTop(0);

		/* Clic sur un item */
		$panel.find('.de-item').on('mousedown', function(e){
			e.preventDefault();
			var idx = parseInt($(this).attr('data-idx'), 10);
			var lbl = decodeURIComponent($(this).attr('data-lbl'));
			$('#twotabsearchtextbox').val(lbl);
			closeBar(); /* autocomplete('close') supprimé → évite le select handler jQuery UI */
			triggerSelectByIdx(idx);
		});
	}

	/* ── Fermeture panel si clic extérieur ── */
	$(document).on('mousedown.de', function(e){
		if($panel && !$(e.target).closest('#de-dd,#deSearchWrapper,#transfertFrm').length) closeBar();
	});

	initPanel();

	/* Masque le dropdown natif jQuery UI */
	$('<style>').text('.ui-autocomplete{display:none!important;}').appendTo('head');
	$('<style>').text('#de-dd .de-item.de-keynav{background:#fff0f2!important;}').appendTo('head');

	/* ══════════════════════════════════════════
	   LOGIQUE 100% IDENTIQUE À L'ANCIENNE VERSION
	══════════════════════════════════════════ */

var _xhr = null;
var _token = 0;

$('#twotabsearchtextbox').autocomplete({
    source: function(query, response) {
    var capturedTerm = query.term;
    var myToken = ++_token;
    if (_xhr) { _xhr.abort(); _xhr = null; }
    _xhr = $.ajax({
            data: { searchPhrase: capturedTerm },
            dataType:"html",
            url: "/search.cfc?method=queryNames&returnformat=json",
            success: function(result) {
    _xhr = null;
    if (myToken !== _token) return;
    expression = capturedTerm;
					var availableTags = [];
					var availableTags1 = [];
					
					if(result != '//["Aucun résultat trouvé"]' && (result != '//[]')){
						var count1=result.split('|').length-1;
						var count=result.split(',').length-1;
						var l=result.substr(3);
						if (count < count1)
						{
							for (var i=0;i<count;i++){
								availableTags[i]=l.substr(1, l.indexOf('|')-1);
								l = l.substr(l.indexOf('|')+1);					
								availableTags1[i]=l.substr(0,l.indexOf(',')-1);
								l = l.substr(l.indexOf(',')+1);						
							}   
							availableTags[count]=l.substr(1, l.indexOf('|')-1);
							l = l.substr(l.indexOf('|')+1);						
							availableTags1[count]=l.substr(0,l.indexOf(']')-2);
						}
						else 
						{
							for (var i=0;i<count1-1;i++){
								pos1=l.indexOf('|');
								pos2=l.indexOf(',');
								if (pos1 < pos2) 
								{
									availableTags[i]=l.substr(1, l.indexOf('|')-1);
									l = l.substr(l.indexOf('|')+1);					
									availableTags1[i]=l.substr(0,l.indexOf(',')-1);
									l = l.substr(l.indexOf(',')+1);	
								}
								else 
								{
									availableTags[i]=l.substr(1, l.indexOf('|')-1);
									l = l.substr(l.indexOf('|')+1);	
									j1=l.substr(0,l.indexOf(',')-1);
									j2=l.substr(l.indexOf(',')+1);
									j=l.indexOf(',');
									availableTags1[i]=l.substr(0,j-1);
									l = l.substr(j+1);											
								}
							}   
							pos1=l.indexOf('|');
							pos2=l.indexOf(',');
							if (pos1 > pos2) 
							{
								availableTags[count1-1]=l.substr(1, l.indexOf('|')-1);
								l = l.substr(l.indexOf('|')+1);						
								availableTags1[count1-1]=l.substr(0,l.indexOf(']')-2);
							}
							else
							{
								availableTags[count]=l.substr(1, l.indexOf('|')-1);
								l = l.substr(l.indexOf('|')+1);						
								availableTags1[count]=l.substr(0,l.indexOf(']')-2);
							}
						}
					}

				table = availableTags1;
tableAvailable = availableTags;
/* jQuery UI attend {label,value} — on wrappe les strings */
var responseItems = availableTags.map(function(s){ return {label:s, value:s}; });
/* Afficher panel AVANT response() — évite que jQuery UI re-appelle source() entre les deux */
if(availableTags.length>0) renderPanel(availableTags, capturedTerm);
else closeBar();
response(responseItems);
				},
				error: function(result) {
                  
                     // alert(messages[2]);  
}			
			});
		},
		minLength: 3,
		autoFocus: true,
		open: function(event, ui){
			/* Empêche l'ouverture du dropdown natif jQuery UI */
			$('#twotabsearchtextbox').autocomplete('widget').hide();
		},
		matchContains: true, 
		scroll: true,
		select: function(event, ui) {
			/* Neutralisé — navigation gérée par triggerSelectByIdx via mousedown
			   Évite ReferenceError sur variables non déclarées (type, idActivite…) */
			return false;
		}
	});

	/* ── Navigation clavier : handler indépendant de jQuery UI ──
	   Bindé sur document en phase capture pour intercepter AVANT jQuery UI */
	document.getElementById('twotabsearchtextbox').addEventListener('keydown', function(e){
		if(!$panel || !$panel.is(':visible')) return;
		var key = e.keyCode;
		if(key===40||key===38){
			e.preventDefault();
			e.stopImmediatePropagation();
			var $items = $panel.find('.de-item');
			if(!$items.length) return;
			$items.removeClass('de-keynav');
			var cur = parseInt($panel.attr('data-keynav')||'-1',10);
			cur = (key===40) ? Math.min(cur+1,$items.length-1) : Math.max(cur-1,0);
			$panel.attr('data-keynav', cur);
			var $it = $items.eq(cur);
			$it.addClass('de-keynav');
			/* Scroll */
			var pt=$panel.scrollTop(), it=$it.position().top+pt, ib=it+$it.outerHeight(), ph=$panel.innerHeight();
			if(ib>pt+ph) $panel.scrollTop(ib-ph);
			else if(it<pt) $panel.scrollTop(it);
		} else if(key===13){
			var kIdx=parseInt($panel.attr('data-keynav')||'-1',10);
			if(kIdx>=0){
				var $focused=$panel.find('.de-item').eq(kIdx);
				if($focused.length){
					e.preventDefault();
					e.stopImmediatePropagation();
					var idx=parseInt($focused.attr('data-idx'),10);
					var lbl=decodeURIComponent($focused.attr('data-lbl'));
					$('#twotabsearchtextbox').val(lbl);
					$panel.removeAttr('data-keynav');
					closeBar();
					triggerSelectByIdx(idx);
				}
			}
		} else if(key===27){
			/* Echap : ferme le panel */
			closeBar();
			$panel.removeAttr('data-keynav');
		}
	}, true); /* true = capture phase, avant jQuery UI */

	$('#twotabsearchtextbox').keydown(function(event){
		if(event.keyCode==13) {  
			closeBar();
			var val = $.trim($(this).val());
			if(tableAvailable.length > 0) {
				triggerSelectByIdx(0);
			} else if (val.length >= 3) {
				$.ajax({
					data: { searchPhrase: val },
					dataType:"html",
					url: "/search.cfc?method=queryNames&returnformat=json",
					success: function(result) {
						if(result==='//["Aucun résultat trouvé"]'||(result==='//[]')){
							$.loadLocalite(val);
							alert(unescape(messages[1]));
						} else {
							var parsed = parseResult(result);
							if (parsed.data.length > 0) {
								table = parsed.data;
								tableAvailable = parsed.tags;
								var firstData = parsed.data[0] || '';
								var lastSeg = (firstData.split('_').pop()||'').toLowerCase().replace(/\s/g,'');
								var isProd = (lastSeg === 'produit' || lastSeg === 'produitt');
								if (isProd && parsed.tags.length === 1) {
									var idActivite = firstData.split('_')[2] || '';
									document.location.href = '/produit.cfm?idactivity=' + idActivite;
								} else {
									triggerSelectByIdx(0);
								}
							}
						}
					},
					error: function(result) { 
						//alert(messages[2]);  
					}				
				}); 
			}
			return false;
		}		
	});

	/* Ferme panel sous 3 caractères + reset position navigation */
	$('#twotabsearchtextbox').on('input', function(){
		if($.trim($(this).val()).length < 3){ closeBar(); }
		if($panel){ $panel.find('.de-keynav').removeClass('de-keynav'); $panel.removeAttr('data-keynav'); }
	});

	(function(){
		jQuery.loadLocalite = function(l){ 
			$(document).load('/ajax/ajaxLocaliteExists1.cfm',{rq:l});
		}
	})(jQuery);

	/* ── triggerSelectByIdx — accès direct par index, sans comparaison fragile ── */
	function triggerSelectByIdx(idx) {
		var row = table[idx];
		if (!row) return;
		var parts      = row.split('_');
		var type       = parts[parts.length-1];
		var idVille    = parts[1]  || '0';
		var idActivite = parts[2]  || '0';
		var idTypePr   = parts[2]  || '0';
		var idTheme    = parts[3]  || '0';
		var idService  = parts[4]  || '0';
		var idLieu     = parts[6]  || '0';
		var idPays     = parts[7]  || '0';
		var texte      = $.trim((parts[0].split('-')[1]) || '');
		var nomLoc     = $.trim(parts[0] || '');
		$('#twotabsearchtextbox').attr('value', nomLoc);
		$('#nomLocality').attr('value', nomLoc);
		$('#filtreTexteSearch').attr('value', texte);
		$('#nomVille').attr('value', idTypePr+'_'+idTheme+'_'+idService+'_0_'+idLieu);
		var t2 = (type||'').toLowerCase().replace(/\s/g,'');
		var url;
		if (t2==='produit'||t2==='produitt') {
			url = '/produit.cfm?idActivity='+idActivite;
		} else if (idPays && idPays!=='0' && idPays!=='') {
			url = '/villeParPays.cfm?idPays='+idPays;
		} else {
			url = '/liste.cfm?idVille='+idVille;
			if (parseInt(idTypePr)>0)  url+='&idTypePrestation='+idTypePr;
			if (parseInt(idTheme)>0)   url+='&idTheme='+idTheme;
			if (parseInt(idService)>0) url+='&idService='+idService;
			if (parseInt(idLieu)>0)    url+='&idLieu='+idLieu;
			if (texte)                 url+='&texteSearch='+encodeURIComponent(texte);
		}
		document.location.href = url.toLowerCase();
	}

	/* ── triggerSelect — identique ancien select ── */
	function triggerSelect(selected){
		var idPays=0, idVille=0, valeurNomVilleAPasser='';
		var split2='0', split3='0', split4='0', split6='0';
		for (var iter=0; iter<table.length; iter++) {
			if (selected==table[iter].split('_')[0]){
				$("#twotabsearchtextbox").attr("value", table[iter].split('_')[0]);
				$("#nomLocality").attr("value", $.trim(table[iter].split('_')[0]));
				var split2=table[iter].split('_')[2]; if(split2=='')split2='0';
				var split3=table[iter].split('_')[3]; if(split3=='')split3='0';
				var split4=table[iter].split('_')[4]; if(split4=='')split4='0';
				var split6=table[iter].split('_')[6]; if(split6=='')split6='0';
				valeurNomVilleAPasser=split2+'_'+split3+'_'+split4+'_0_'+split6;
				$("#nomVille").attr("value", valeurNomVilleAPasser);
				var type=table[iter].split('_')[table[iter].split('_').length-1];
				idVille=table[iter].split('_')[1];
				var idTypePrestation=table[iter].split('_')[2];
				var idActivite=table[iter].split('_')[2];
				var idTheme=table[iter].split('_')[3];
				var idService=table[iter].split('_')[4];
				var idLangue=table[iter].split('_')[5];
				var idLieu=table[iter].split('_')[6];
				idPays=table[iter].split('_')[7];
				var texteSearch=$.trim((table[iter].split('_')[0]).split('-')[1]);
				$("#filtreTexteSearch").attr("value",texteSearch);
				var nomLocality=$("#nomLocality").val();
				if (selected!=="Aucun résultat trouvé"){
					var locUrl;
					var t2=(type||'').toLowerCase().replace(/\s/g,'');
					if(t2==='produit'||t2==='produitt'){
						locUrl='/produit.cfm?idActivity='+idActivite;
					}else if(idPays!=''&&idPays!=0){
						locUrl='/villeParPays.cfm?idPays='+idPays;
					}else{
						locUrl='/liste.cfm?idVille='+idVille;
						if(idTypePrestation>0)locUrl+='&idTypePrestation='+idTypePrestation;
						if(idTheme>0)locUrl+='&idTheme='+idTheme;
						if(idService>0)locUrl+='&idService='+idService;
						if(idLieu>0)locUrl+='&idLieu='+idLieu;
						if(texteSearch&&texteSearch.length>0)locUrl+='&texteSearch='+encodeURIComponent(texteSearch);
					}
					document.location.href=locUrl.toLowerCase();
				}else{
					$("#twotabsearchtextbox").val('');
				}
				break;
			}
		}
	}

	$("#btnRechercher").click(function(){
		var checkIn=false;
		$.ajax({
			data: { searchPhrase: $("#twotabsearchtextbox").val() },
			dataType:"html",
			url: "/search.cfc?method=queryNames&returnformat=json",
			success: function(result) {
				var valeurNomVilleAPasser='';
				var idPays=0;
				var split2='0', split3='0', split4='0', split6='0';
				if(result!='//["Aucun résultat trouvé"]'&&(result!='//[]')){
					for (var iter=0; iter<table.length; iter++) {
						if($("#twotabsearchtextbox").val()==table[iter].split('_')[0]){
							$("#twotabsearchtextbox").attr("value", table[iter].split('_')[0]);
							$("#nomLocality").attr("value", $.trim(table[iter].split('_')[0]));
							var split2=table[iter].split('_')[2]; if(split2=='')split2='0';
							var split3=table[iter].split('_')[3]; if(split3=='')split3='0';
							var split4=table[iter].split('_')[4]; if(split4=='')split4='0';
							var split6=table[iter].split('_')[6]; if(split6=='')split6='0';
							valeurNomVilleAPasser=split2+'_'+split3+'_'+split4+'_0_'+split6;
							$("#nomVille").attr("value", valeurNomVilleAPasser);
							idPays=table[iter].split('_')[7];
							var nomLocality=$("#nomLocality").val();
							if(idPays!=''&&idPays!=0){
								var locUrl='/villeParPays.cfm?idPays='+idPays;
							}else{
								if($("#rewrite").val()==1){									
									var locUrl='/activites/'+(nomLocality.replace(/ /g,'-'))+'.html';
								}else{
									var locUrl='/liste.cfm?idVille='+table[iter].split('_')[1];
								}
							}
							checkIn=true;
							document.location.href=locUrl.toLowerCase();
						}
					}
					if(checkIn===false){
						for (var iter=0; iter<1; iter++) {
							$("#twotabsearchtextbox").attr("value", table[iter].split('_')[0]);
							$("#nomLocality").attr("value", $.trim(table[iter].split('_')[0]));
							var split2=table[iter].split('_')[2]; if(split2=='')split2='0';
							var split3=table[iter].split('_')[3]; if(split3=='')split3='0';
							var split4=table[iter].split('_')[4]; if(split4=='')split4='0';
							var split6=table[iter].split('_')[6]; if(split6=='')split6='0';
							valeurNomVilleAPasser=split2+'_'+split3+'_'+split4+'_0_'+split6;
							$("#nomVille").attr("value", valeurNomVilleAPasser);
							idPays=table[iter].split('_')[7];
							var nomLocality=$("#nomLocality").val();
							if(idPays!=''&&idPays!=0){
								var locUrl='/villeParPays.cfm?idPays='+idPays;
							}else{
								var locUrl='/activites/'+(nomLocality.replace(/ /g,'-'))+'.html';
							}
							document.location.href=locUrl.toLowerCase();
						}
					}
				}else{
					$.loadLocalite($("#twotabsearchtextbox").val());
					alert(unescape(messages[1]));
				}
			},
			error: function(result) {}
		}); 
		return false;
	});

	$("#twotabsearchtextbox").focus(function(){
		table=[]; tableAvailable=[];
		$(this).css("background","white");
	});

	$(".loupe").click(function(event){
		var ctrlOK=true;
		var ville=$("#nomVille").val();
		var detailActivite=ville.split('_')[3];
		var nomLocality=$("#nomLocality").val();
		if(!nomLocality||ville==0){return false;}
		if(ctrlOK){
			if(nomLocality!=0){ 
				if(detailActivite=='0'){
					var locUrl='/activites/'+(nomLocality.replace(/ /g,'-'))+'.html';
					document.location.href=locUrl.toLowerCase();
				}else document.location.href='gotopage.cfm?nomVille='+detailActivite;
			}else return false;
		}
	});

	$(".twitter-typeahead").css("display","block");

	$('#btn_plusseo').click(function(){
		var $this=$(this), $id=$(this).attr('id').split('_')[1];
		$('#'+$id).toggleClass(function(){
			if(!$(this).is(':visible')) $this.html('<i class="icon-up-open" title="Masquer"></i> Masquer'); 
			else $this.html('<i class="icon-down-open" title="Voir plus"></i> Voir plus');
		});
	});

	$('.menu-topd').click(function(){
		var obj=$(this).data('objet'), $v=$(this).data('ville');
		$('button[data-objet='+obj+']').removeClass('active');
		$(this).addClass('active');
		$.ajax({
			url:"ajax/ajaxHomeTopVilles.cfm", type:"POST", data:{ville:$v}, cache:false,
			beforeSend: function(){ $('#'+obj).html('<img src="img/loader.gif" alt="" style="border:none">'); },
			success: function(data){ $('#'+obj).html(data); }
		});
	});

	$("#btn_topd_1").trigger("click");

}); /* fin document.ready */

function setEtab(el,tab){
	document.querySelectorAll('.etab').forEach(function(t){t.classList.remove('active');});
	el.classList.add('active');
	document.querySelectorAll('.explorer-grid').forEach(function(g){g.style.display='none';});
	document.getElementById('exp-'+tab).style.display='grid';
}