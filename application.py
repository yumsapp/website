from flask import render_template, request, send_file, session, redirect
from application import db
from application.models import Restaurant, Offer, Award
from datetime import datetime
import qrcode
import cStringIO
import random
from app import application
from cheapyums.core.utils import convertUTCToTimezone


#import admintasks

@application.route("/a/<restaurant>/award/<awardCode>", methods=['GET', 'POST'])
def viewAward(restaurant, awardCode):
    db.session.connection(execution_options={'isolation_level': "READ COMMITTED"})
    awd = Award.query.filter_by(code=awardCode, restaurant_code=restaurant).first()
    if awd is None:
        print "Award not found"
        return ""

    off = Offer.query.filter_by(code=awd.offer_code, restaurant_code=restaurant).first()
    if off is None:
        print "Offer not found"
        return ""

    res = Restaurant.query.filter_by(code=restaurant).first()
    if res is None:
        print "Restaurant not found"
        return ""

    if awd.customers is None:
        if request.method == "GET":
            return render_template('pre_award.html', maxCustomers=off.max_customers,updateURL="/a/{0}/award/{1}".format(restaurant, awardCode))
        if request.method == "POST":
            cust = int(request.form.get("customers", 0))
            if 0 < cust <= off.max_customers:
                awd.customers = cust
                db.session.commit()
            else:
                return render_template('pre_award.html', maxCustomers=off.max_customers, updateURL="/a/{0}/award/{1}".format(restaurant, awardCode))

    hours = ""
    if res.bf_start is not None and res.bf_end is not None:
        hours = "{0} - {1}".format(res.bf_start.strftime("%-I:%M %p"), res.bf_end.strftime("%-I:%M %p"))
    if res.lu_start is not None and res.lu_end is not None:
        if hours != "":
            hours = "{0} / ".format(hours)
        hours = "{0}{1} - {2}".format(hours,res.lu_start.strftime("%-I:%M %p"), res.lu_end.strftime("%-I:%M %p"))
    if res.di_start is not None and res.di_end is not None:
        if hours != "":
            hours = "{0} / ".format(hours)
        hours = "{0}{1} - {2}".format(hours,res.di_start.strftime("%-I:%M %p"), res.di_end.strftime("%-I:%M %p"))

    data={
        "minPercent": off.min_offer_percent,
        "maxPercent": off.min_offer_percent + off.off_peak_bonus + off.random_offer_bonus,
        "startDate": off.valid_start_date.strftime("%-m/%-d/%y"),
        "endDate": off.valid_end_date.strftime("%-m/%-d/%y"),
        "peakPercent": off.min_offer_percent,
        "offPeakPercent": off.min_offer_percent + off.off_peak_bonus,
        "hours": hours,
        "customers":awd.customers,
        "status": awd.status
    }
    if awd.status == "REDEEMED":
        data["discount"]= awd.offer_percent
        data["redemptionDate"] = awd.redemption_ts.date().strftime("%-m/%-d/%y")
        data["redemptionTime"] = awd.redemption_ts.time().strftime("%-I:%M %p")

    db.session.close()
    if request.method == "POST":
        return redirect("/a/{0}/award/{1}".format(restaurant, awardCode))
    return render_template("award.html", restaurant=restaurant, awardCode=awardCode, data=data)


@application.route("/a/<restaurant>/qrcode/<awardCode>")
def QRCode(restaurant, awardCode):
    db.session.connection(execution_options={'isolation_level': "READ COMMITTED"})
    awd = Award.query.filter_by(code=awardCode, restaurant_code=restaurant).first()
    if awd is None:
        return ""

    off = Offer.query.filter_by(code=awd.offer_code, restaurant_code=restaurant).first()
    if off is None:
        return ""

    if awd.customers is None:
        return ""

    img_buf = cStringIO.StringIO()
    img = qrcode.make("http://www.cheapyums.com/r/{0}/redemption/{1}".format(restaurant,awardCode))
    img.save(img_buf)
    img_buf.seek(0)
    return send_file(img_buf, mimetype='image/png')


@application.route("/r/<restaurant>/quicklogin/<loginCode>")
def quickLogin(restaurant, loginCode):
    db.session.connection(execution_options={'isolation_level': "READ COMMITTED"})
    res = Restaurant.query.filter_by(code=restaurant).first()
    if res is None:
        return "The page you are trying to access does not exist!"
    if res.password == loginCode:
        session["restaurant"] = restaurant
        session["loggedIn"] = True
        return "You are now logged in as {0}".format(res.name)
    else:
        session["restaurant"] = None
        session["loggedIn"] = False
    return "The page you are trying to access does not exist!"


## DATE CONDITIONS STILL NOT PROPERLY CHECKED
@application.route("/r/<restaurant>/redemption/<awardCode>")
def redeemOffer(restaurant, awardCode):
    db.session.connection(execution_options={'isolation_level': "READ COMMITTED"})
    if "restaurant" not in session or "loggedIn" not in session:
        return "Only restaurants can process award redemptions.  If you are a restaurant, please log in!"

    if session["restaurant"] != restaurant or session["loggedIn"] != True:
        return "Only restaurants can process award redemptions.  If you are a restaurant, please log in!"

    awd = Award.query.filter_by(code=awardCode, restaurant_code=restaurant).first()
    if awd is None:
        return "This offer is not valid in this establishment."

    off = Offer.query.filter_by(code=awd.offer_code, restaurant_code=restaurant).first()
    if off is None:
        return "This offer is not valid in this establishment."

    res = Restaurant.query.filter_by(code=restaurant).first()
    if res is None:
        return "This offer is not valid in this establishment."

    if awd.status == "REDEEMED":
        return "This award was redeemed on {0} at {1}.<p>Total discount: {2}%<p>Number of Customers: {3}".format(awd.redemption_ts.date(), awd.redemption_ts.time(), awd.offer_percent, awd.customers)

    now = convertUTCToTimezone(datetime.utcnow(), res.timezone)

    # Check to see if the award is currently valid based on the start and end dates
    if now.date() < off.valid_start_date or now.date() > off.valid_end_date:
        return "This offer is not currently valid.  This offer is only valid from {0} to {1}.".format(off.valid_start_date.strftime("%-m/%-d/%y"), off.valid_end_date.strftime("%-m/%-d/%y"))

    # Offer is valid.  Now let us set up all the offer details

    print "Current Time is {0}".format(now)
    print now.time()

    isPeak = False
    if res.bf_start is not None and res.bf_end is not None:
        if res.bf_start <= now.time() < res.bf_end:
            print "Breakfast Rush Hour"
            isPeak = True
    if res.lu_start is not None and res.lu_end is not None:
        if res.lu_start <= now.time() < res.lu_end:
            print "Lunch Rush Hour"
            isPeak = True
    if res.di_start is not None and res.di_end is not None:
        if res.di_start <= now.time() < res.di_end:
            print "Dinner Rush Hour"
            isPeak = True

    print isPeak

    print "Minimum Offer % : {0}".format(off.min_offer_percent)
    print "Offpeak Bonus % : {0}".format(off.off_peak_bonus)
    print "Random Offer Bonus % : {0}".format(off.random_offer_bonus)
    bonus = random.randrange(0, off.random_offer_bonus+1)
    print "Bonus {0}".format(bonus)

    offerValue = off.min_offer_percent
    if not isPeak:
        offerValue = offerValue + off.off_peak_bonus
    offerValue = offerValue + bonus
    print "Total Offer Value = {0}".format(offerValue)

    awd.redemption_ts = datetime.utcnow()
    awd.status = "REDEEMED"
    awd.offer_percent = offerValue
    db.session.commit()
    db.session.close()

    return "Offer has been accepted.  Total offer value: {0}".format(offerValue)


@application.route('/', methods=['GET', 'POST'])
@application.route('/index', methods=['GET', 'POST'])
def index():
    return ""

if __name__ == '__main__':
    application.run(host='0.0.0.0')